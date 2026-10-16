#include <stdio.h>

int main(void) {
    // 数组容量 5，预留一个空位，最多保存 4 个元素。
    int queue[5] = {0};
    int front = 0;
    int rear = 0;

    for (int value = 10; value <= 40; value += 10) {
        if ((rear + 1) % 5 != front) {
            queue[rear] = value;
            rear = (rear + 1) % 5;
        }
    }

    int popped = 0;
    for (int i = 0; i < 2; i++) {
        if (front != rear) {
            popped = queue[front];
            front = (front + 1) % 5;
        }
    }

    // rear 从 4 回到 0，随后到 1；观察物理位置和逻辑顺序。
    for (int value = 50; value <= 60; value += 10) {
        if ((rear + 1) % 5 != front) {
            queue[rear] = value;
            rear = (rear + 1) % 5;
        }
    }
    printf("front = %d, rear = %d\n", front, rear);
    return 0;
}
