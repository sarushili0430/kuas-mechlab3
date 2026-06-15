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

#ifndef _PID
#define _PID

class PID{
	public:
		double ff_kp;
		double kp;
		double ki;
		double kd;

		double max_output;
		double min_output;

		double integral;
		double prev_error;

		PID(double kp, double ki, double kd, double ff_kp, double max_output, double min_output):
			kp(kp),
			ki(ki),
			kd(kd),
			ff_kp(ff_kp),
			max_output(max_output),
			min_output(min_output),
			prev_error(0.0),
			integral(0.0){}
		
        PID(){}
        
		~PID(){}

		double calculate(double setpoint, double pv, double dt);

};
#endif
