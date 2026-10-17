#include <stdio.h>

int main(void) {
    int capacity = 1000000;
    int values[capacity];
    values[0] = 10;
    values[capacity - 1] = 20;
    int *p = &values[capacity - 1];
    *p += 5;
    // 滚动演示区查看数组末尾；未赋值的位置保持灰色。
    printf("首项=%d，末项=%d\n", values[0], values[capacity - 1]);
    return 0;
}
