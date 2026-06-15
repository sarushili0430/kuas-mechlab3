#ifndef _MOTORCTRL
#define _MOTORCTRL

#include "mbed.h"
#include "RotaryEncoder.hpp"
#include "PIDmotor.hpp"

class MotorCtrl{
    public:
        MotorCtrl(PinName m_a, PinName m_b, PinName enc_a, PinName enc_b): 
            motor(m_a, m_b),
            enc(enc_a, enc_b){}

        PIDmotor       motor;
        RotaryEncoder  enc;

        void set_encoder_resolution(float resol);
        void init();
        void start();
        void update();
        void setSpeed(float rpm);        

        float getMotorSpeed();
};

#endif