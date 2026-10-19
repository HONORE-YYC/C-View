// typedef 为已有类型取别名；结构体把相关变量组织在一起。
#include <stdio.h>
#define CAPACITY 5
typedef int ElemType;
typedef struct Stack {
    ElemType data[CAPACITY];
    int top;
} Stack;

void push(Stack *s, ElemType value) {
    if (s->top < CAPACITY - 1) {
        s->top++;
        s->data[s->top] = value;
    }
}

int main(void) {
    Stack s = {{0}, -1};
    // 可单步展开函数，观察 -> 修改调用者的结构体成员。
    push(&s, 10);
    push(&s, 20);
    int i = s.top;
    ElemType popped = s.data[i];
    s.top--;
    // 结构体按值复制；修改副本不会改变原对象。
    Stack copy = s;
    copy.data[0] = 99;
    printf("出栈：%d，原栈底：%d，副本栈底：%d\n", popped, s.data[0], copy.data[0]);
    return 0;
}
