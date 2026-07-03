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
static const int MOTOR_DIR[4] = {+1, -1, +1, -1};

static const float SP_FULL      = 10.5f;  // Pi 側 wheel_setpoint と揃える
static const int   PWM_MAX      = 4000;   // pwm テレメトリの分母
static const int   PWM_CAP      = 4000;   // =100%(4000/4000)。満舵で常時フルduty。電流/発熱最大、短時間で
static const int   PWM_FREQ_HZ  = 20000;  // 可聴域より上
static const int   WATCHDOG_MS  = 500;    // 指令が途絶えたら全停止
static const int   TELEMETRY_MS = 20;     // テレメトリ 50 Hz

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
    pc.set_blocking(false);

    float sp[4] = {0.0f, 0.0f, 0.0f, 0.0f};
    char rx[64];
    size_t rx_len = 0;
    Timer cmd_timer, tel_timer;
    cmd_timer.start();
    tel_timer.start();

    while (true) {
        // --- 受信: 終端 'd' までためて "s1/s2/s3/s4" をパース ---
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
            } else if (rx_len < sizeof(rx) - 1) {
                rx[rx_len++] = c;
            } else {
                rx_len = 0;  // 壊れたパケットは捨てて次の 'd' で再同期
            }
        }

        // --- ウォッチドッグ: USB 抜け・Pi 停止でも確実に止める ---
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
