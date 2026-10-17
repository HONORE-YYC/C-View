#include <stdio.h>

int main(void) {
    long count;
    double price;
    char grade;
    char name[16];

    // 输入示例：3000000000 2.5 A Alice
    printf("请输入数量、单价、等级和姓名：\n");
    int matched = scanf("%ld %lf %c %15s", &count, &price, &grade, name);
    if (matched == 4) {
        double total = count * price;
        char next = grade + 1;
        printf("%s: 数量=%ld, 总价=%lf, 等级=%c, 下一等级=%c\n",
               name, count, total, grade, next);
    }
    return 0;
}
