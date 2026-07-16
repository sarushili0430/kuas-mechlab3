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
static const char SERVO_EOP       = 'a';    // サーボ指令パケットの終端
// スルーレート上限: 出力パルス幅を 1 フレームあたり最大この[us]だけ目標へ寄せる。
// 40us/frame × 50fps = 2000us/s ≈ 180°/s（全幅 2000us = 180°）。大きな角度指令でも
// DS3225 を全速スラムさせず、突入/ストール電流サージとアームの振り切れを抑える。
// 速く/遅くしたい時はこの値だけ調整（大=速い＝電流大 / 小=遅い＝電流小）。
static const int  SERVO_SLEW_US_PER_FRAME = 40;

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

// ===== Servo ソフト PWM（モーターの HW PWM とは独立系統の別モジュール）=====
// 駆動系(TIM1/3/16/17) と us_ticker(TIM2) で HW タイマが枯渇し 50Hz サーボ用の空き ch が
// 無い。→ us_ticker ベースの Ticker/Timeout でソフト PWM を生成（HW PWM 非依存＝配線ピン
// は任意 GPIO）。車輪の L298NMotor（ハード PWM）とは別クラス・別パラメータで完全に分離。
// 20ms 毎に frame_isr が有効パルスのピンを上げ、各パルス幅[us]後の Timeout で下げる。
//
// スルーレート制限: 指令は「目標パルス幅」として受け、実際の出力パルス幅は 1 フレーム
// あたり最大 SERVO_SLEW_US_PER_FRAME[us] だけ目標へ寄せる。大きな角度指令でも DS3225 を
// 全速スラムさせず、突入/ストール電流サージとアームの振り切れ（オーバーシュート）を防ぐ。
// 初回指令だけは前回位置が無いのでスナップ（初動は従来どおり）。起動時は目標=0=無パルスで
// 最初の指令までアームは動かない。車輪と違いウォッチドッグでは中立化せず、最後の目標を保持
// し続ける。ジッタは割込み遅延程度（数us≪パルス幅）でサーボは許容。
class ServoSoftPwm {
public:
    ServoSoftPwm() : pin0_(A0), pin1_(A1) {}  // s1=shoulder A0 / s2=elbow A1

    // Ticker を起動して 50Hz フレームを回し始める（main から 1 回だけ呼ぶ）。
    void init() {
        pin0_ = 0;
        pin1_ = 0;
        frame_.attach(callback(this, &ServoSoftPwm::frame_isr),
                      std::chrono::microseconds(SERVO_PERIOD_US));
    }

    // 目標パルス幅[us]をセット（安全帯にクランプ）。反映はフレーム毎にスルーレート制限付き。
    // main ループ（非 ISR）からのみ呼ぶ。出力側 current_us_ の書き手は ISR だけなので競合しない。
    void set_target(int ch, int us) {
        if (us < SERVO_MIN_US) us = SERVO_MIN_US;
        if (us > SERVO_MAX_US) us = SERVO_MAX_US;
        target_us_[ch] = us;
    }

    // 受領確認エコー用: 受理済みの目標（クランプ後）を返す。
    int target(int ch) const { return target_us_[ch]; }

private:
    void ch0_low() { pin0_ = 0; }
    void ch1_low() { pin1_ = 0; }

    // 目標へ最大 SERVO_SLEW_US_PER_FRAME/フレームだけ寄せ、今フレームのパルス幅を返す。
    // 0 = 未指令（無パルス）。current_us_ の唯一の書き手（ISR 内のみ）。
    int step(int ch) {
        int tgt = target_us_[ch];
        if (tgt == 0) { current_us_[ch] = 0; return 0; }  // 未指令: 無パルス
        int cur = current_us_[ch];
        if (cur == 0) {
            cur = tgt;                                     // 初回: 前回位置が無いのでスナップ
        } else {
            int d = tgt - cur;                             // スルーレート制限
            if (d >  SERVO_SLEW_US_PER_FRAME) d =  SERVO_SLEW_US_PER_FRAME;
            if (d < -SERVO_SLEW_US_PER_FRAME) d = -SERVO_SLEW_US_PER_FRAME;
            cur += d;
        }
        if (cur < SERVO_MIN_US) cur = SERVO_MIN_US;        // 念のため安全帯に収める
        if (cur > SERVO_MAX_US) cur = SERVO_MAX_US;
        current_us_[ch] = cur;
        return cur;
    }

    // フレーム先頭（20ms 毎）: 各 ch をスルーレート制限で 1 歩進め、有効パルスのピンを上げ、
    // 幅[us]後に下げる Timeout を仕込む。
    void frame_isr() {
        const int c0 = step(0);
        if (c0 > 0) {
            pin0_ = 1;
            off0_.attach(callback(this, &ServoSoftPwm::ch0_low),
                         std::chrono::microseconds(c0));
        }
        const int c1 = step(1);
        if (c1 > 0) {
            pin1_ = 1;
            off1_.attach(callback(this, &ServoSoftPwm::ch1_low),
                         std::chrono::microseconds(c1));
        }
    }

    DigitalOut pin0_, pin1_;                          // s1=shoulder A0 / s2=elbow A1
    Ticker     frame_;                                // 20ms フレーム先頭
    Timeout    off0_, off1_;                          // 立下りワンショット
    volatile int target_us_[SERVO_COUNT] = {0, 0};    // main が書く目標（0=未指令）
    int          current_us_[SERVO_COUNT] = {0, 0};   // ISR 専有の現在出力幅（0=無パルス）
};

static ServoSoftPwm servos;

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
    servos.init();               // A0/A1 をソフト PWM(Ticker/Timeout)で 50Hz 駆動（モーターと独立）
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
                    for (int i = 0; i < SERVO_COUNT; i++) servos.set_target(i, u[i]);
                    char ack[40];
                    int n = snprintf(ack, sizeof(ack), "srv %d %d\n",
                                     servos.target(0), servos.target(1));
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
