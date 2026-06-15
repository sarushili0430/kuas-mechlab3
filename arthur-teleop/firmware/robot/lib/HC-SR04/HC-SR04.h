#pragma once
#include "mbed.h"


class HCSR04 {
   DigitalIn echo_ ;
   DigitalInOut trigger_; 
   
   Timer t_;
   int time_us_;
   int distance_;
    
    
public:

    HCSR04(PinName echo, PinName trigger);
    
    void reading();
    void fastTimeReading();
    
    int getTime();
    int getDistance();
    
};