#include <stdio.h>

int main() {
    int arr[100] = {1, 2, 3, 4, 5}; 
    int n = 5;  
    int val = 90;

    arr[n] = val; 
    n++;

    for (int i = 0; i < n; i++) {
        printf("%d ", arr[i]);
    }
    return 0;
}
