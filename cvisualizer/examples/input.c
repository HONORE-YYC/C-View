#include <stdio.h>
#include <iostream>
using namespace std;

int main(void) {
    long long count;
    double price;
    char grade;
    char name[16];

    // 输入示例：8000000000 2.5 A Alice
    printf("请输入数量、单价、等级和姓名：\n");
    int matched = scanf("%lld %lf %c %15s", &count, &price, &grade, name);
    if (matched == 4) {
        double total = count * price;
        char next = grade + 1;
        cout << name << ": 数量=" << count << ", 总价=" << total
             << ", 等级=" << grade << ", 下一等级=" << next << endl;
    }
    // 也可以把上面的 scanf 语句替换为以下两行：
    // cin >> count >> price >> grade >> name;
    // int matched = 4;
    // cin 会按目标类型读取；字符数组仍需为末尾的结束符预留容量。
    return 0;
}
