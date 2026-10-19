#include <stdio.h>
#include <stdbool.h>
#include <math.h>

int main(void) {
    // 勾股距离、取整与比较；观察布尔结果由灰色变绿/红再淡出。
    double x = 3.0;
    double y = 4.0;
    double distance = sqrt(pow(x, 2) + pow(y, 2));
    double direct = hypot(x, y);
    double rounded = round(2.6);
    double magnitude = fabs(-2.5);
    bool nearby = distance <= 5.0;
    bool outside = distance > 5.0;
    int skipped = 0;
    bool safe = nearby || ++skipped > 0;
    if (nearby && !outside) {
        x = floor(distance / 2);
    }
    double wave = sin(0.0) + cos(0.0);
    double logarithm = log2(8.0);
    printf("distance=%f, nearby=%d, outside=%d, skipped=%d\n",
           distance, nearby, outside, skipped);
    return 0;
}
