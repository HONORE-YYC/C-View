#include <stdio.h>
#include <cstdlib>
#define OK 1

// 可修改所有名称；修改后请保持引用一致。
// 节点恰有两个成员：一个数值数据成员，一个指向自身的指针。
typedef int ElemType;
typedef struct LNode {
    ElemType data;
    struct LNode *next;
} LNode, *LinkList;
typedef int Status;

Status InitList(LinkList &L) {
    L = new LNode;
    L->next = NULL;
    return OK;
}

// 函数名可自由修改，画面始终跟随下面的指针赋值。
void AddAfter(LinkList previous, ElemType value) {
    LinkList node = new LNode;
    node->data = value;
    node->next = previous->next;
    previous->next = node;
}

int main() {
    LinkList L;
    InitList(L);             // 头节点的数据不参与存储

    // 头插：先连接新节点，再改变头节点的 next。
    // 点击调用行号，可逐句展开 AddAfter 内部的连接过程。
    for (int i = 1; i <= 3; i++) {
        AddAfter(L, i * 10);
    }

    // 尾插：移动 tail 找到尾节点，再接入值为 40 的节点。
    LinkList tail = L;
    while (tail->next != NULL) {
        tail = tail->next;
    }
    LinkList added = new LNode;
    added->data = 40;
    added->next = NULL;
    tail->next = added;

    // 删除值为 20 的节点：先绕过它，再释放节点。
    LinkList previous = L->next;
    LinkList removed = previous->next;
    previous->next = removed->next;
    delete removed;
    removed = NULL;

    // 遍历：最终链表为 30 -> 10 -> 40 -> NULL。
    int count = 0;
    int sum = 0;
    LinkList cursor = L->next;
    while (cursor != NULL) {
        printf("%d ", cursor->data);
        sum += cursor->data;
        count++;
        cursor = cursor->next;
    }
    printf("\n节点数：%d，总和：%d\n", count, sum);
    return 0;
}
