#include <stdio.h>
#include <stdbool.h>

int main(void) {
    const double price = 12.75;
    int whole = (int)price;
    double half = static_cast<double>(whole) / 2;
    long long population = 8000000000LL;
    bool ready = true;
    char grade = 'A';

    // 去掉指针的只读限定：原对象可写时才允许修改。
    int score = 3;
    const int *view = &score;
    int *editable = const_cast<int *>(view);
    *editable = 7;
    const int fixed = 9;
    const int *protected_view = &fixed;
    // fixed 本身只读，即使 const_cast 后也不能写入。
    printf("whole=%d, half=%f, population=%lld, ready=%d, grade=%c, score=%d\n",
           whole, half, population, ready, grade, score);
    return 0;
}
