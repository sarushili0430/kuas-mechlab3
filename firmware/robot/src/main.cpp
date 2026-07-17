#include "mbed.h"

#include <cstdio>

// ===== Tomoe-11 ピン割当（docs: robot-pinout-power-reference.pdf §1a が正） =====
// L298N は ENA/ENB ジャンパ ON のまま、IN ピンを直接 PWM する
// （モーター 1 個につき PWM 2 本の sign-magnitude 駆動。EN ピンは使わない）。
// _ALT トークンはタイマー選択用の firmware-only 表記で、はんだパッドは silk どおり。
struct MotorPins {
    PinName in1;  // 正転側
    PinName in2;  // 逆転側
};
static const MotorPins MOTOR_PINS[4] = {
    {D7, D8},                // s1/ch0: M1（公称 FL）PA_8 TIM1_CH1 / PA_9 TIM1_CH2 — 実機物理=後左 BL
    {D5, D4},                // s2/ch1: M2（公称 BL）PB_4 TIM3_CH1 / PB_5 TIM3_CH2 — 実機物理=前左 FL
    {PA_7_ALT2, PA_6_ALT0},  // s3/ch2: M3（公称 FR）D11 TIM17_CH1 / D12 TIM16_CH1 — 実機物理=後右 BR
    {D2, PA_11},             // s4/ch3: M4（公称 BR）PA_10 TIM1_CH3 / PA_11 TIM1_CH4 — 実機物理=前右 FR
};

// 各輪の正転符号: +1 なら +setpoint で前進、-1 で反転。
// 2026-06-16 のジョグ試験でハード確定（arthur/dev で end-to-end 検証済み）。
// 2026-07-03 基盤を上下逆に取り付けたため、全 4 輪の回転方向を反転
// （旧 {-1,+1,-1,+1} → 全符号反転）。チャンネル⇔コーナー対応は不変。
// 物理コーナー: ch0=後左(BL), ch1=前左(FL), ch2=後右(BR), ch3=前右(FR)。
// 左側=ch0+ch1 / 右側=ch2+ch3 はスキッドステアの左右グルーピングと一致するので、
// ホスト側 kinematics（s1,s2=左 / s3,s4=右）は無改修でよい。
// 1 輪が逆回転する場合は該当 MOTOR_DIR[i] の符号を反転して再フラッシュ（scripts/pi-jog.py で確認）。
// 2026-07-15 この機体で全輪ジョグ再検証: ch0(後左)と ch3(前右)が逆転していたため両符号を反転
// （{+1,-1,+1,-1} → {-1,-1,+1,+1}）。機体固有の配線差につき friend の develop とは意図的に相違。
static const int MOTOR_DIR[4] = {-1, -1, +1, +1};

static const float SP_FULL      = 10.5f;  // Pi 側 wheel_setpoint と揃える
static const int   PWM_MAX      = 4000;   // pwm テレメトリの分母
static const int   PWM_CAP      = 4000;   // =100%(4000/4000)。満舵で常時フルduty。電流/発熱最大、短時間で
static const int   PWM_FREQ_HZ  = 20000;  // 可聴域より上
static const int   WATCHDOG_MS  = 500;    // 指令が途絶えたら全停止
static const int   TELEMETRY_MS = 20;     // テレメトリ 50 Hz

// ===== Servo（アーム）: DS3225 ×2、ソフト PWM（Ticker/Timeout）で任意 GPIO を駆動 =====
// 信号線のみ Nucleo（3.3 V パルスで駆動可）。V+/GND は専用サーボレール（§4）へ。
// 駆動系(TIM1/3/16/17)＋us_ticker(TIM2) で HW タイマ枯渇 → ソフト PWM。s1=shoulder A0,
// s2=elbow A1（任意 GPIO 可）。旧 PB_14/PB_15(TIM15) は GND 短絡で放棄。
// 駆動パケット（終端 'd'）とは独立の別パケット（終端 'a'）。protocol.py と一致。
static const int  SERVO_COUNT     = 2;
static const int  SERVO_PERIOD_US = 20000;  // 50 Hz
static const int  SERVO_MIN_US    = 500;    // 安全下限（protocol.py と一致）
static const int  SERVO_MAX_US    = 2500;   // 安全上限（protocol.py と一致）
static const int  SERVO_SLEW_US_PER_FRAME = 25;  // 出力の追従上限 25us/20ms ≈ 112°/s（Home ジャンプ等の突入電流対策）
static const char SERVO_EOP       = 'a';    // サーボ指令パケットの終端

// ===== 車載 LED: 緑単色 on/off（docs: robot-pinout-power-reference §3c）=====
// D3(PB_3) の DigitalOut（220Ω 直列）。終端 'l' の独立パケット "v/l"（v=0|1）で
// 受け、"led v" をエコー。QR タスクの色表示は将来 RGB 化（現状は緑 on/off のみ）。
static const PinName LED_PIN = D3;
static const char    LED_EOP = 'l';   // LED 指令パケットの終端

class L298NMotor {
public:
    explicit L298NMotor(const MotorPins& p) : in1_(p.in1), in2_(p.in2) {
        in1_.period_us(1000000 / PWM_FREQ_HZ);
        in2_.period_us(1000000 / PWM_FREQ_HZ);
        apply(0);
    }
    // pwm: -PWM_MAX..PWM_MAX（PWM_CAP で飽和）。符号が回転方向。
    // 正転は IN1 に PWM・IN2=0、逆転はその逆（fast-decay / coast）。
    void apply(int pwm) {
        if (pwm >  PWM_CAP) pwm =  PWM_CAP;
        if (pwm < -PWM_CAP) pwm = -PWM_CAP;
        pwm_ = pwm;
        float duty = float(pwm >= 0 ? pwm : -pwm) / PWM_MAX;
        in1_.write(pwm > 0 ? duty : 0.0f);
        in2_.write(pwm < 0 ? duty : 0.0f);
    }
    int pwm() const { return pwm_; }

private:
    PwmOut in1_, in2_;
    int pwm_ = 0;
};

// ===== Servo ソフト PWM: Ticker/Timeout で任意 GPIO を 50Hz 駆動 =====
// 駆動系(TIM1/3/16/17) と us_ticker(TIM2) で HW タイマが枯渇し 50Hz サーボ用の空き ch が
// 無い。→ us_ticker ベースの Ticker/Timeout でソフト PWM を生成（HW PWM 非依存＝配線ピン
// は任意 GPIO）。20ms 毎に servo_frame_isr が有効パルスのピンを上げ、各パルス幅[us]後の
// Timeout で下げる。出力(servo_us)は目標(servo_target_us)へ毎フレーム最大
// SERVO_SLEW_US_PER_FRAME だけ追従する（急峻なステップ目標に DS3225 が最大トルクで
// 飛びつく＝突入電流を機体側で吸収）。起動時は無パルスでアームは脱力しており、現在姿勢が
// 不明でランプ起点を作れないため初回指令のみ直行。車輪と違いウォッチドッグでは中立化せず、
// 最後の目標を保持し続ける。ジッタは割込み遅延程度（数us≪パルス幅）でサーボは許容。
static DigitalOut servo_pin0(A0);          // s1=shoulder
static DigitalOut servo_pin1(A1);          // s2=elbow
static Ticker     servo_frame;             // 20ms フレーム先頭
static Timeout    servo_off0, servo_off1;  // 立下りワンショット
static volatile int servo_target_us[SERVO_COUNT] = {0, 0};  // 受理済み指令（クランプ後）
static int servo_us[SERVO_COUNT] = {0, 0};                  // 実際に出している幅（ISR 専有）

static void servo0_low() { servo_pin0 = 0; }
static void servo1_low() { servo_pin1 = 0; }

// 出力パルス幅を目標へ 1 フレームぶん近づける。cur==0（初回・無パルス）は直行。
static int servo_slew(int cur, int target) {
    if (cur == 0 || target == 0) return target;
    if (target > cur + SERVO_SLEW_US_PER_FRAME) return cur + SERVO_SLEW_US_PER_FRAME;
    if (target < cur - SERVO_SLEW_US_PER_FRAME) return cur - SERVO_SLEW_US_PER_FRAME;
    return target;
}

// フレーム先頭（20ms 毎）: スルーレート制限で目標へ近づけ、有効パルスのピンを上げて
// 幅[us]後に下げる Timeout を仕込む。
static void servo_frame_isr() {
    servo_us[0] = servo_slew(servo_us[0], servo_target_us[0]);
    servo_us[1] = servo_slew(servo_us[1], servo_target_us[1]);
    if (servo_us[0] > 0) {
        servo_pin0 = 1;
        servo_off0.attach(&servo0_low, std::chrono::microseconds(servo_us[0]));
    }
    if (servo_us[1] > 0) {
        servo_pin1 = 1;
        servo_off1.attach(&servo1_low, std::chrono::microseconds(servo_us[1]));
    }
}

static void servo_init() {
    servo_pin0 = 0;
    servo_pin1 = 0;
    servo_frame.attach(&servo_frame_isr, std::chrono::microseconds(SERVO_PERIOD_US));  // 50 Hz
}

// ch=0:shoulder(A0) / ch=1:elbow(A1)。us を安全帯にクランプして目標に据える。
// 出力は servo_frame_isr がスルーレート制限付きで追従（反映は次フレーム以降）。
static void servo_apply_us(int ch, int us) {
    if (us < SERVO_MIN_US) us = SERVO_MIN_US;
    if (us > SERVO_MAX_US) us = SERVO_MAX_US;
    servo_target_us[ch] = us;
}

static BufferedSerial pc(USBTX, USBRX, 115200);

static int elapsed_ms(const Timer& t) {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
               t.elapsed_time())
        .count();
}

int main() {
    L298NMotor motors[4] = {
        L298NMotor(MOTOR_PINS[0]), L298NMotor(MOTOR_PINS[1]),
        L298NMotor(MOTOR_PINS[2]), L298NMotor(MOTOR_PINS[3]),
    };
    servo_init();                // A0/A1 をソフト PWM(Ticker/Timeout)で 50Hz 駆動
    DigitalOut led(LED_PIN, 0);  // 起動時は消灯

    pc.set_blocking(false);

    float sp[4] = {0.0f, 0.0f, 0.0f, 0.0f};
    char rx[64];
    size_t rx_len = 0;
    Timer cmd_timer, tel_timer;
    cmd_timer.start();
    tel_timer.start();

    while (true) {
        // --- 受信: 終端 'd'=駆動 "s1/s2/s3/s4" / 'a'=サーボ / 'l'=LED をパース ---
        char c;
        while (pc.read(&c, 1) == 1) {
            if (c == 'd') {
                rx[rx_len] = '\0';
                float v[4];
                if (sscanf(rx, "%f/%f/%f/%f", &v[0], &v[1], &v[2], &v[3]) == 4) {
                    for (int i = 0; i < 4; i++) {
                        sp[i] = v[i];
                        motors[i].apply(int(MOTOR_DIR[i] * v[i] / SP_FULL * PWM_CAP));
                    }
                    cmd_timer.reset();
                }
                rx_len = 0;
            } else if (c == SERVO_EOP) {
                // サーボパケット "us1/us2"。cmd_timer は触らない（サーボは車輪
                // ウォッチドッグ対象外＝指令保持）。受領確認 "srv us1 us2" をエコー。
                rx[rx_len] = '\0';
                int u[SERVO_COUNT];
                if (sscanf(rx, "%d/%d", &u[0], &u[1]) == SERVO_COUNT) {
                    for (int i = 0; i < SERVO_COUNT; i++) servo_apply_us(i, u[i]);
                    char ack[40];
                    int n = snprintf(ack, sizeof(ack), "srv %d %d\n",
                                     servo_target_us[0], servo_target_us[1]);
                    pc.write(ack, n);
                }
                rx_len = 0;
            } else if (c == LED_EOP) {
                // LED パケット "v"（0|1）。cmd_timer は触らない（LED は状態保持）。
                // 受領確認 "led v" をエコー。
                rx[rx_len] = '\0';
                int v;
                if (sscanf(rx, "%d", &v) == 1) {
                    led = (v != 0) ? 1 : 0;
                    char ack[16];
                    int n = snprintf(ack, sizeof(ack), "led %d\n", led.read());
                    pc.write(ack, n);
                }
                rx_len = 0;
            } else if (rx_len < sizeof(rx) - 1) {
                rx[rx_len++] = c;
            } else {
                rx_len = 0;  // 壊れたパケットは捨てて次の終端で再同期
            }
        }

        // --- ウォッチドッグ: USB 抜け・Pi 停止でも確実に止める（車輪のみ） ---
        if (elapsed_ms(cmd_timer) > WATCHDOG_MS) {
            for (int i = 0; i < 4; i++) {
                sp[i] = 0.0f;
                motors[i].apply(0);
            }
        }

        // --- テレメトリ: 50 Hz（エンコーダ未実装のため rpm は常に 0） ---
        if (elapsed_ms(tel_timer) >= TELEMETRY_MS) {
            tel_timer.reset();
            char line[120];
            int n = snprintf(
                line, sizeof(line),
                "sp %.2f %.2f %.2f %.2f | rpm 0.00 0.00 0.00 0.00 | pwm %d %d %d %d\n",
                sp[0], sp[1], sp[2], sp[3],
                motors[0].pwm(), motors[1].pwm(), motors[2].pwm(), motors[3].pwm());
            pc.write(line, n);
        }
        ThisThread::sleep_for(1ms);
    }
}
