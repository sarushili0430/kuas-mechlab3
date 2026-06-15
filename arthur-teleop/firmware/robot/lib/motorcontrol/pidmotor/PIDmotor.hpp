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

#ifndef _PIDmotor
#define _PIDmotor

#include "mbed.h"
#include "PID.hpp"
#include <time.h>

class PIDmotor{
    public:
        PIDmotor(PinName motorB, PinName motorA) : pwm_motor_b(motorB), pwm_motor_a(motorA) {} 
        Ticker timer_motor_control;
        PID pid;

        float target_speed;
        float current_speed;
        int max_pid_output;
        int min_pid_output;
        int pid_output;
        float loop_freq;
        int dt;
        int runaway_count;  // consecutive samples where encoder strongly disagrees with setpoint

        void set_pid_gain(float kp, float ki, float kd, float kff);
        void start();
        void init();
        void update_current_speed(float rpm);
        void set_max_min_pid_output(int, int);
        void set_target_speed(float rpm);

    private:
        PwmOut pwm_motor_a;
        PwmOut pwm_motor_b;    

        void move_forward(int);
        void move_backward(int);
        void generate_motor_pwm(int);
        void control();

};

#endif
