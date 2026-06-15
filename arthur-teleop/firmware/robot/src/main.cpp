#include "mbed.h"
#include "SerialROS2.hpp"
#include "MotorControl.hpp"   // also pulls in PIDmotor.hpp + RotaryEncoder.hpp
#include "Servo.h"            // 2-DOF arm servos (DS3225) on TIM15
#include "BNO055.h"           // IMU over I2C1

// ---------------------------------------------------------------------------
// ML3 robot drivetrain — 4-motor skid-steer teleop (Team 11, "Tomoe-11").
//
// Four independently-addressable wheels over two L298N boards, each wheel with
// its quadrature encoder wired to the Nucleo. The Pi sends four setpoints per
// packet ("s1/s2/s3/s4/d"); each maps to one wheel:
//
//   motor1 = front-left (FL)    motor2 = back-left (BL)    -> LEFT  L298N (A)
//   motor3 = front-right (FR)   motor4 = back-right (BR)   -> RIGHT L298N (B)
//   left side = motor1 + motor2      right side = motor3 + motor4
//
// All four are closed-loop-CAPABLE MotorCtrl objects (PIDmotor + RotaryEncoder).
// On the current kit the encoders are effectively dead (flaky JGA25 hall PCBs +
// the pull-up fix can silence a high-resistance line), so they read ~0 and the
// loop runs OPEN-LOOP: current_speed=0 -> error=setpoint -> PWM saturates to the
// clamp. PWM_CAP (not the setpoint magnitude) therefore sets the real speed. If
// an encoder turns out to be alive, that wheel becomes true closed-loop for free.
//
// Setpoint==0 is a hard stop (PWM forced to 0) inside PIDmotor::control(), so
// 'q' reliably stops all four wheels regardless of phantom encoder noise.
// NOTE: the integral is only drained on stop, so press 'q' between a forward
// and a reverse command for a crisp reversal (back-to-back w->s has windup lag).
//
// PIN MAP — permanent build (docs/superpowers/specs/2026-06-02-nucleo-pin-assignment-design.md):
//   MotorCtrl(m_a, m_b, enc_a, enc_b)  -> drive m_a/m_b, encoder CLK=enc_a SIG=enc_b
//   Drive PWM pins all on distinct NORMAL timer channels (never CHxN):
//     TIM1: CH1=D7 CH2=D8 CH3=D2 CH4=PA_11 | TIM3: CH1=D5 CH2=D4 | TIM17_CH1=PA_7_ALT2 | TIM16_CH1=PA_6_ALT0
//     (M3 MUST use PA_7_ALT2 / PA_6_ALT0: plain PA_7=TIM1_CH1N, plain PA_6=TIM3_CH1 which collides with D5.)
//   Encoder InterruptIn pins on distinct EXTI lines (no two share a pin number):
//     M1: 10,2  M2: 7,6  M3: 8,9  M4: 12,15
//   Servos on TIM15 (independent of the drive timers): PB_14_ALT0=CH1, PB_15_ALT1=CH2, 50 Hz.
//     (MUST use the ALT tokens: bare PB_14/PB_15 = TIM1_CH2N/CH3N — complementary, on a drive timer.)
//   IMU BNO055 on I2C1: D14=SDA, D15=SCL.
// ---------------------------------------------------------------------------

// Bring-up PWM clamp, in µs against the 4000 µs (250 Hz) period set by init().
// 4000 = full speed (100% duty); 1500 ≈ 37.5%. Raise toward 4000 once each
// wheel's direction is verified with the per-wheel jog keys (1-4) on the Pi.
#define PWM_CAP 1500

// PERMANENT-BUILD mapping (spec §4a/§4b). Relocated from the 2026-05-29 breadboard
// pins for tangle-free routing; datasheet-audited. motorN -> wheel MN (M1=FL, M2=BL,
// M3=FR, M4=BR); drive m_a/m_b = L298N IN1/IN2; encoder tuple = (CLK=Hall A, SIG=Hall B)
// on that motor's own corner. DIRn (below) flips the sign so a POSITIVE setpoint drives
// that wheel FORWARD — but the signs are PROVISIONAL for this new wiring and MUST be
// re-confirmed by the per-wheel jog test (keys 1-4), exactly as on 2026-05-29.
MotorCtrl motor1(D7, D8,            D6, PB_2);      // M1 Front-Left  : drive TIM1 C1/C2 (D7/D8)    -> L298N-A, enc PB_10/PB_2
MotorCtrl motor2(D5, D4,            D9, D10);       // M2 Back-Left   : drive TIM3 C1/C2 (D5/D4)    -> L298N-A, enc PC_7/PB_6
MotorCtrl motor3(PA_7_ALT2, PA_6_ALT0, PC_8, PC_9);    // M3 Front-Right : drive TIM17/TIM16 (D11/D12) -> L298N-B, enc PC_8/PC_9 (5V-tolerant FT; A0/A1=PA_0/PA_1 are 3.3V-only TTa)
MotorCtrl motor4(D2, PA_11,         PC_12, PA_15); // M4 Back-Right  : drive TIM1 C3/C4 (D2/PA_11)  -> L298N-B, enc PC_12/PA_15

// Per-wheel forward sign: +1 if +setpoint already drives forward, -1 to invert.
#define DIR1 (-1)   // ch0 motor1 = physical Back-Left  — FORWARD confirmed by jog 2026-06-16
#define DIR2 (+1)   // ch1 motor2 = physical Front-Left — FORWARD confirmed by jog 2026-06-16
#define DIR3 (-1)   // ch2 motor3 = physical Back-Right — FORWARD confirmed by jog 2026-06-16
#define DIR4 (+1)   // ch3 motor4 = physical Front-Right — FORWARD confirmed by jog 2026-06-16

// --- Arm: 2-DOF DS3225 servos on TIM15. ALT tokens are MANDATORY (spec §4d): bare
// PB_14/PB_15 resolve to TIM1_CH2N/CH3N — complementary outputs on a drive timer. The
// Servo ctor sets a 20 ms/50 Hz frame and centers to 0.5 (safe mid) on boot.
Servo s1(PB_14_ALT0);   // shoulder
Servo s2(PB_15_ALT1);   // elbow

// --- IMU: BNO055 over I2C1 (D14=SDA, D15=SCL). ---
BNO055 imu(D14, D15);

SerialROS2 pc(USBTX, USBRX, 115200);

float setpoint1 = 0.0;   // motor1 front-left  (FL)
float setpoint2 = 0.0;   // motor2 back-left   (BL)
float setpoint3 = 0.0;   // motor3 front-right (FR)
float setpoint4 = 0.0;   // motor4 back-right  (BR)

// Packet from the Pi is "s1/s2/s3/s4/d" -> data[0..3]. The Pi always sends 4.
void setMotorSpeed(float* data){
    if (data != nullptr){
        setpoint1 = data[0];
        setpoint2 = data[1];
        setpoint3 = data[2];
        setpoint4 = data[3];
    }
}

int main() {
    pc.init();
    pc.recvCallback = &setMotorSpeed;

    motor1.motor.set_pid_gain(20.0, 0.001, 0.005, 0.0);
    motor2.motor.set_pid_gain(20.0, 0.001, 0.005, 0.0);
    motor3.motor.set_pid_gain(20.0, 0.001, 0.005, 0.0);
    motor4.motor.set_pid_gain(20.0, 0.001, 0.005, 0.0);

    motor1.set_encoder_resolution(0.0007633);
    motor2.set_encoder_resolution(0.0007633);
    motor3.set_encoder_resolution(0.0007633);
    motor4.set_encoder_resolution(0.0007633);

    motor1.init();
    motor2.init();
    motor3.init();
    motor4.init();

    // after init(): clamp only — period stays 4000 µs
    motor1.motor.set_max_min_pid_output(PWM_CAP, -PWM_CAP);
    motor2.motor.set_max_min_pid_output(PWM_CAP, -PWM_CAP);
    motor3.motor.set_max_min_pid_output(PWM_CAP, -PWM_CAP);
    motor4.motor.set_max_min_pid_output(PWM_CAP, -PWM_CAP);

    motor1.start();
    motor2.start();
    motor3.start();
    motor4.start();

    // IMU bring-up (mirrors exercise 1-4): check() prints 1 if the BNO055 answers on I2C1.
    imu.setmode(OPERATION_MODE_IMUPLUS);
    printf("imu check %d\n", imu.check());
    imu.set_orientation(DEGREES);

    // Servo / IMU bring-up state (loop-local).
    float arm_p   = 0.5f;   // servo sweep position, 0..1 = 0..180 deg
    int   arm_dir = 1;      // sweep direction
    int   imu_div = 0;      // throttles the IMU read to ~1 per 100 loops

    while(1) {
        pc.recvVals();

        // FORCED OPEN-LOOP: pin current_speed=0 instead of motorN.update() (which
        // would push enc.rpm in). The kit's encoders are flaky/partially-alive and,
        // when all 4 motors run, PWM noise injects phantom pulses that flipped the
        // PID output sign between identical commands (observed 2026-05-29: a FORWARD
        // command intermittently drove M2 backward). Pinning pv=0 makes output
        // deterministic: PWM = sign(DIRn*setpoint) * clamp, i.e. the exact per-wheel
        // direction validated by the jog test. getMotorSpeed() still reports raw
        // enc.rpm as telemetry only — it is NOT in the control path.
        motor1.motor.update_current_speed(0.0);  motor1.setSpeed(DIR1 * setpoint1);
        motor2.motor.update_current_speed(0.0);  motor2.setSpeed(DIR2 * setpoint2);
        motor3.motor.update_current_speed(0.0);  motor3.setSpeed(DIR3 * setpoint3);
        motor4.motor.update_current_speed(0.0);  motor4.setSpeed(DIR4 * setpoint4);

        // Diagnostic: setpoints | measured rpm (0 if encoder dead) | PWM per motor.
        printf("sp %.1f %.1f %.1f %.1f | rpm %.1f %.1f %.1f %.1f | pwm %d %d %d %d\n",
               setpoint1, setpoint2, setpoint3, setpoint4,
               motor1.getMotorSpeed(), motor2.getMotorSpeed(),
               motor3.getMotorSpeed(), motor4.getMotorSpeed(),
               motor1.motor.pid_output, motor2.motor.pid_output,
               motor3.motor.pid_output, motor4.motor.pid_output);

        // --- Servo wiring test: slow, gentle sweep of both channels between 0.30 and
        // 0.70 (~54..126 deg, clear of the end-stops). Narrow once the arm is mounted.
        arm_p += arm_dir * 0.001f;
        if (arm_p >= 0.70f) { arm_p = 0.70f; arm_dir = -1; }
        if (arm_p <= 0.30f) { arm_p = 0.30f; arm_dir = +1; }
        s1.write(arm_p);
        s2.write(arm_p);

        // --- IMU wiring test: print Euler angles ~10x/s (throttled so the I2C read
        // doesn't stall the loop). A static 0/0/0 => check SDA/SCL/power.
        if (++imu_div >= 100) {
            imu_div = 0;
            imu.get_angles();
            printf("imu r %.1f p %.1f y %.1f\n", imu.euler.roll, imu.euler.pitch, imu.euler.yaw);
        }

        wait_us(1000);
    }
}
