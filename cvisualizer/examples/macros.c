#include <cstdlib>
#include <stdio.h>
#define N 4
#define DOUBLE(x) ((x) * 2)

int main(void) {
    int x;
    int pending;
    int a[N];
    x = abs(-3);
    a[0] = x;
    x = DOUBLE(x) + 1;
    srand(7);
    for (int i = 1; i < N; i++) {
        a[i] = rand() % 10;
    }
    printf("x=%d, a[3]=%d\n", x, a[3]);
    return 0;
}
