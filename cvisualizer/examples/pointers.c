#include <stdio.h>
#include <stddef.h>

void add_ten(int *value) {
    *value += 10;
}

int main(void) {
    int x = 3;
    int *p = &x;
    *p = 7;

    int values[4] = {1, 2, 3, 4};
    p = values;
    int i = 0;
    for (i = 0; i < 4; i++) {
        *p = values[i] + 1;
        p++;
    }

    int *q = &values[1];
    *q = x;
    add_ten(q);
    p = NULL;
    printf("x=%d, values[1]=%d\n", x, values[1]);
    return 0;
}
