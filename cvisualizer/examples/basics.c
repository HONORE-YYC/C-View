#include <stdio.h>
#include <stdlib.h>
#define DOUBLE(x) ((x) * 2)

int main(void) {
    // 灰框等待赋值；复制时观察绿色箭头。宏在执行前展开。
    int pending;
    int source = abs(-3);
    int target;
    target = source;
    target = DOUBLE(target) + 1;
    double average = target / 2.0;
    printf("target=%d, average=%f\n", target, average);
    return 0;
}
