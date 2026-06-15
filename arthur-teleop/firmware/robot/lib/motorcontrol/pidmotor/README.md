# PIDmotor
The code is for control angular velocity of motor by PID feedback controller.
This code have been tested on NUCLEO-F091RC. 
The code develop based on mbed libs.

########################## Example #################################
```
#include "mbed.h"
#include "RotaryEncoder.hpp"
#include "PIDmotor.hpp"

PIDmotor pidMotor(D3, D4);
RotaryEncoder enc(D6, D7);

float setpoint = 60.0;

int main() {
    pidMotor.set_pid_gain(10.0, 0.0001, 0.0001, 0.0);

    enc.init();
    pidMotor.init();

    enc.start();
    pidMotor.start();

    while(1) {
        pidMotor.update_current_speed(enc.rpm);
        pidMotor.set_target_speed(setpoint);

        printf("%f, %f\n",setpoint, enc.rpm);
        ThisThread::sleep_for(1ms);
    }
}
```
####################################################################
