#include <stdio.h>

int main(void) {
    int data[6] = {2, 4, 6};
    int length = 3;
    int stack[6] = {0};
    int top = -1;
    int queue[6] = {0};
    int front = 0;
    int rear = 0;

    // 同一循环，把顺序表的元素送入栈和队列。
    for (int i = 0; i < length; i++) {
        if (top < 5) {
            top++;
            stack[top] = data[i];
        }
        if ((rear + 1) % 6 != front) {
            queue[rear] = data[i];
            rear = (rear + 1) % 6;
        }
    }

    int popped = stack[top];
    top--;
    int first = queue[front];
    front = (front + 1) % 6;

    // 修改顺序表，同步观察三个结构各自的状态。
    int position = 1;
    for (int i = length; i > position; i--) {
        data[i] = data[i - 1];
    }
    data[position] = 9;
    length++;
    queue[rear] = 99;
    rear = (rear + 1) % 6;
    printf("stack popped = %d, queue first = %d\n", popped, first);
    return 0;
}
