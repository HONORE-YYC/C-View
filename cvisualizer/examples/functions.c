#include <stdio.h>

int twice(int value) {
    int result = value * 2;
    return result;
}

void add_to_array(int data[], int length, int amount) {
    for (int i = 0; i < length; i++) {
        data[i] = data[i] + amount;
    }
}

int sum_array(int data[], int length) {
    int sum = 0;
    for (int i = 0; i < length; i++) {
        sum += data[i];
    }
    return sum;
}

int main(void) {
    int source = 3;
    int answer = twice(source);
    int numbers[4] = {1, 2, 3, 4};
    add_to_array(numbers, 4, answer);
    int total = sum_array(numbers, 4);
    printf("answer=%d, total=%d\n", answer, total);
    return 0;
}
