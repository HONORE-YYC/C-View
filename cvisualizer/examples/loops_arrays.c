#include <stdio.h>
#define N 4

int main(void) {
    // i/j 移动下标箭头，元素复制展示赋值箭头。
    int a[N] = {2, 4, 6, 8};
    int i = 0;
    int j = N - 1;
    for (i = 0; i < 2; i++) {
        a[j] = a[i];
        j--;
    }
    int sum = 0;
    for (i = 0; i < N; i++) {
        if (a[i] == 2) {
            continue;
        }
        sum += a[i];
    }
    int count = 3;
    while (count > 0) {
        count--;
    }
    printf("sum=%d, count=%d\n", sum, count);
    return 0;
}
