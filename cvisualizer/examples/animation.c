#include <stdio.h>
#define N 4

int main(void) {
    int source = 7;
    int target;
    int a[N] = {2, 4, 6, 8};
    int i = 0;
    int j = N - 1;

    target = source;
    for (i = 0; i < 2; i++) {
        a[j] = a[i];
        j--;
    }
    target = a[2];
    printf("target=%d\n", target);
    return 0;
}
