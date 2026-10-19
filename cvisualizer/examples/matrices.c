// 前排方框表示行，后面的叠层表示这一行的元素。
// 执行到 a[i][j] 时，对应元素抽出显示，随后收回。
#include <stdio.h>

int main(void) {
    int a[2][3] = {{1, 2, 3}, {4, 5, 6}};
    int total = 0;
    for (int i = 0; i < 2; i++) {
        for (int j = 0; j < 3; j++) {
            a[i][j] += 1;
            total += a[i][j];
        }
    }
    // 两个元素同时抽出，绿色箭头演示复制。
    a[1][2] = a[0][1];
    printf("累加结果：%d\n", total);

    // 五列及以上使用代表性叠层，操作时仍显示准确下标。
    int wide[2][8] = {{0}};
    wide[1][7] = a[1][2];

    // 连续超过十行内容相同时折叠；操作中的行保留显示。
    int repeated[24][3] = {{0}};
    repeated[12][1] = 5;
    return 0;
}
