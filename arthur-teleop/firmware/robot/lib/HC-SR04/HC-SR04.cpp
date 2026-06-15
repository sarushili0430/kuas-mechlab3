#include "HC-SR04.h"
#include <chrono>



HCSR04::HCSR04 (PinName echo, PinName trigger):
    echo_(echo), trigger_(trigger, PIN_OUTPUT, OpenDrain, 0){};
    
void HCSR04::reading(){
    t_.reset();
    
    trigger_ = true;
    wait_us(10);
    trigger_ = false;
         
    //waits for the echo pin to activate then starts to measure time
    while(!echo_);
    t_.start();
    while(echo_);
    //time stops being measured once echo is deactivated.
    t_.stop();
    //time measured in microseconds to increase the accuracy then the distance is scaled up into mm.
    time_us_ =  std::chrono::duration_cast<std::chrono::microseconds>(t_.elapsed_time()).count();
    //distance stored in baseDistance_ variable
    distance_ = (160*time_us_) / 1000;
    thread_sleep_for(100);
}

void HCSR04::fastTimeReading(){
    t_.reset();
    
    trigger_ = true;
    wait_us(10);
    trigger_ = false;
         
    //waits for the echo pin to activate then starts to measure time
    while(!echo_);
    t_.start();
    while(echo_);
    //time stops being measured once echo is deactivated.
    t_.stop();
    time_us_ = std::chrono::duration_cast<std::chrono::microseconds>(t_.elapsed_time()).count();
    
}

int HCSR04::getTime(){
    return time_us_;
}

int HCSR04::getDistance(){
    return distance_;
}

