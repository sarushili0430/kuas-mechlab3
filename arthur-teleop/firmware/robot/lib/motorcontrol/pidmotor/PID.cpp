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

#include "PID.hpp"

double PID::calculate(double setpoint, double pv, double dt){
	double error = setpoint - pv;
	double FFPout = this->ff_kp * setpoint;
	double Pout = this->kp * error;
	
	this->integral += error * dt;
	double Iout = this->ki * this->integral;

	double derivative = (error - this->prev_error)/dt;
	double Dout = this->kd * derivative;

	double output =  FFPout + Pout + Iout + Dout;

	if (output > this->max_output) output = this->max_output;
	else if (output < this->min_output) output = this->min_output;

	this->prev_error = error;

	return output;
}
