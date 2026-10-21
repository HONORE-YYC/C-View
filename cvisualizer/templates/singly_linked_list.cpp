#include <iostream>
using namespace std;

// 名称均可修改，但修改后请同步更新引用。
// 保持一个数值数据成员、一个指向自身的指针成员，程序会识别为单链表。
typedef int ElemType;
typedef struct LNode {
    ElemType data;
    struct LNode *next;
} LNode, *LinkList;

void CreateList_H(LinkList &L, int n) {
    L = new LNode;
    L->next = NULL;
    for (int i = 0; i < n; i++) {
        LinkList p = new LNode;
        cin >> p->data;
        p->next = L->next;
        L->next = p;
    }
}

int main() {
    // 最先声明的该类型指针作为头指针。
    LinkList L;
    int n = 3;  // 可修改节点数量。输入示例：1 2 3
    cout << "请输入 " << n << " 个整数：" << endl;
    // 点击这条调用语句的行号，可展开查看函数内部的构建过程。
    CreateList_H(L, n);

    cout << "头插法构建的链表：";
    LinkList p = L->next;
    while (p != NULL) {
        cout << p->data << " ";
        p = p->next;
    }
    cout << endl;
    return 0;
}
