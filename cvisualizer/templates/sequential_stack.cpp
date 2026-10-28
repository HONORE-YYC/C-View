#include <iostream>
#include <cstdlib>
using namespace std;
#define MAXSIZE 100
#define OK 1
#define ERROR -1
#define OVERFLOW -2

typedef int SElemType;
typedef int Status;

// 名称可修改；请保持声明顺序：栈底指针、栈顶指针、int 容量。
// 两个指针指向同一种数值类型，top 指向下一个可入栈的位置。
typedef struct {
    SElemType *base;
    SElemType *top;
    int stacksize;
} SqStack;

Status InitStack(SqStack &S) {
    S.base = new SElemType[MAXSIZE];
    if (!S.base) exit(OVERFLOW);
    S.top = S.base;
    S.stacksize = MAXSIZE;
    return OK;
}

// 函数名可自由修改；动画由实际的数据写入和指针移动驱动。
Status Put(SqStack &S, SElemType value) {
    if (S.top - S.base == S.stacksize) return ERROR;
    *S.top = value;
    S.top++;
    return OK;
}

Status Take(SqStack &S, SElemType &value) {
    if (S.top == S.base) return ERROR;
    --S.top;
    value = *S.top;
    return OK;
}

int main() {
    SqStack S;
    InitStack(S);
    // 超过 10 个元素时，中间自动折叠；可修改数量或元素值。
    for (int value = 1; value <= 12; value++) {
        Put(S, value);
    }
    SElemType popped;
    Take(S, popped);
    cout << "第一次出栈：" << popped << endl;
    Put(S, 99);  // 入栈时，左侧仍保留上次出栈的 12。
    Take(S, popped);
    cout << "再次出栈：" << popped << endl;
    Take(S, popped);
    cout << "最后出栈：" << popped << endl;
    // 此时栈内为 10 到 1，左侧保留最近出栈的 11。
    // 需要释放存储时，可执行 delete[] S.base; 并将两个指针设为 NULL。
    return 0;
}
