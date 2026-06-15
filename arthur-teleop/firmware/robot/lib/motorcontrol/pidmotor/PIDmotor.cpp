/*
# Copyright 2023 FIBO
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# Authors: Natee #
*/

#include "PIDmotor.hpp"

void PIDmotor::init(){
    this->max_pid_output = 4000;
    this->min_pid_output = -4000;
    this->loop_freq = 0.04;
    this->runaway_count = 0;

    dt = loop_freq * 1000000;
    set_max_min_pid_output(max_pid_output, min_pid_output);

    pwm_motor_a.period_us(max_pid_output);
    pwm_motor_b.period_us(max_pid_output);
}

void PIDmotor::set_pid_gain(float kp, float ki, float kd, float kff){
    pid.kp = kp;
    pid.ki = ki;
    pid.kd = kd;
    pid.ff_kp = kff;
}

void PIDmotor::set_max_min_pid_output(int max, int min){
    pid.max_output = max;
    pid.min_output = min;
}

void PIDmotor::start(){
    timer_motor_control.attach(callback(this, &PIDmotor::control), loop_freq);
}

void PIDmotor::control(){
    // Setpoint-zero hard stop: forces PWM=0 regardless of encoder reading,
    // so a phantom-reading encoder cannot trick the PID into braking PWM
    // and accelerating the motor in the wrong direction at "stop".
    if (target_speed == 0.0f) {
        pid_output = 0;
        runaway_count = 0;
        // Drain the integrator on every stop. Without this, a long run in
        // one direction winds the integral up to max, and the next opposite
        // command can't produce a negative PID output until the integral
        // unwinds — which (with dt in microseconds) takes seconds. Result:
        // motor refuses to reverse direction after a long forward run.
        pid.integral = 0.0;
        pid.prev_error = 0.0;
        generate_motor_pwm(pid_output);
        return;
    }

    pid_output = int(pid.calculate(target_speed, current_speed, dt));

    // Runaway watchdog: if the encoder reports speed much larger than the
    // commanded speed with the opposite sign, the encoder's direction sense
    // is lying and the PID is being driven into saturation. After a few
    // consecutive bad samples (~150 ms at 40 ms loop), cut PWM so the motor
    // can coast back to rest rather than spinning at full speed forever.
    float abs_target  = (target_speed  >= 0) ? target_speed  : -target_speed;
    float abs_current = (current_speed >= 0) ? current_speed : -current_speed;
    bool sign_disagree = (target_speed * current_speed) < 0.0f;
    bool magnitude_blown = abs_current > (4.0f * abs_target + 20.0f);

    if (sign_disagree && magnitude_blown) {
        runaway_count++;
        if (runaway_count >= 4) {
            pid_output = 0;
        }
    } else {
        runaway_count = 0;
    }

    generate_motor_pwm(pid_output);
}

void PIDmotor::generate_motor_pwm(int pulseWidth){
    if (pulseWidth == 0) {
        pwm_motor_a.pulsewidth_us(0);
        pwm_motor_b.pulsewidth_us(0);
    } else if (pulseWidth < 0) {
        move_backward(-1 * pulseWidth);
    } else {
        move_forward(pulseWidth);
    }
}

void PIDmotor::update_current_speed(float rpm){
    current_speed = rpm;
}

void PIDmotor::set_target_speed(float rpm){
    target_speed = rpm;
}

void PIDmotor::move_forward(int pwm){
    pwm_motor_a.pulsewidth_us(pwm);
    pwm_motor_b.pulsewidth_us(0);
}

void PIDmotor::move_backward(int pwm){
    pwm_motor_a.pulsewidth_us(0);
    pwm_motor_b.pulsewidth_us(pwm);
}

