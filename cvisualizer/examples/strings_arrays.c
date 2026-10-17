#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int sum(const int values[], const int count) {
    int result = 0;
    for (int i = 0; i < count; i++) {
        result += values[i];
    }
    return result;
}

int main(void) {
    int values[] = {2, 4, 6};
    int count = atoi("3");
    int copy[count];
    for (int i = 0; i < count; i++) {
        copy[i] = values[i];
    }
    int total = sum(copy, count);

    char first[] = "C";
    char title[24];
    strcpy(title, first);
    strcat(title, " View");
    long length = strlen(title);
    int same = strcmp(title, "C View");
    printf("%s, 长度=%ld, 总和=%d\n", title, length, total);
    return 0;
}
