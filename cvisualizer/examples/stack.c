#include <stdio.h>

int main(void) {
    int stack[6] = {0};
    int top = -1;

    // 入栈：先移动栈顶，再存放元素。
    for (int value = 10; value <= 30; value += 10) {
        if (top < 5) {
            top++;
            stack[top] = value;
        }
    }

    int popped = 0;
    if (top >= 0) {
        popped = stack[top];
        top--;
    }

    if (top < 5) {
        top++;
        stack[top] = 99;
    }
    printf("popped = %d, top = %d\n", popped, top);
    return 0;
}
