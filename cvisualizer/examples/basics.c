#include <stdio.h>

int main(void) {
    // 同一段代码中混合变量、数组、条件与循环。
    int sum = 0;
    int data[5] = {0};
    for (int i = 0; i < 5; i++) {
        if (i == 2) {
            continue;
        }
        data[i] = i * 2;
        sum += data[i];
    }

    int count = 3;
    while (count > 0) {
        count--;
    }
    double average = sum / 5.0;
    printf("sum = %d, average = %f\n", sum, average);
    return 0;
}
