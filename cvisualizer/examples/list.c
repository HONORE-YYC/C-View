#include <stdio.h>

int main(void) {
    int data[8] = {10, 20, 30, 40};
    int length = 4;
    int position = 1;
    int value = 99;

    // 在下标 1 处插入：从后往前移动，避免覆盖。
    if (length < 8 && position >= 0 && position <= length) {
        for (int i = length; i > position; i--) {
            data[i] = data[i - 1];
        }
        data[position] = value;
        length++;
    }

    // 删除下标 3：向前移动，最后缩短有效长度。
    position = 3;
    if (position >= 0 && position < length) {
        for (int i = position; i < length - 1; i++) {
            data[i] = data[i + 1];
        }
        length--;
    }

    int found = -1;
    for (int i = 0; i < length; i++) {
        if (data[i] == 99) {
            found = i;
            break;
        }
    }
    printf("length = %d, found = %d\n", length, found);
    return 0;
}
