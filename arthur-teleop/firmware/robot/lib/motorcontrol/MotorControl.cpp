#include "MotorControl.hpp"

void MotorCtrl::set_encoder_resolution(float resol){
    this->enc.encoder_resolution = resol;
}

void MotorCtrl::init(){
    this->enc.init();
    this->motor.init();
}

void MotorCtrl::start(){
    this->enc.start();
    this->motor.start();
}

void MotorCtrl::update(){
    this->motor.update_current_speed(this->enc.rpm);
}

void MotorCtrl::setSpeed(float rpm){
    this->motor.set_target_speed(rpm);
}

float MotorCtrl::getMotorSpeed(){
    return this->enc.rpm;
}