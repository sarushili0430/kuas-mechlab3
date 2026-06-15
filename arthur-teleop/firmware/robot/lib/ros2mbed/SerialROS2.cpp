#include "SerialROS2.hpp"
#include <string.h>

// Tokenize text on `sep`. Commits the trailing token at '\0' too,
// so callers don't need a trailing separator.
char** split(char sep, char text[]) {
    char* token = nullptr;
    int len = 0;

    char** tokens = nullptr;
    int n_tokens = 0;

    int n = (int)strlen(text);
    for (int i = 0; i <= n; i++) {
        char c = text[i];
        bool is_sep = (c == sep || c == '\n' || c == '\0');
        if (!is_sep) {
            token = (char*)realloc(token, sizeof(char) * (len + 1));
            token[len++] = c;
        } else {
            if (len > 0) {
                token = (char*)realloc(token, sizeof(char) * (len + 1));
                token[len] = '\0';

                tokens = (char**)realloc(tokens, sizeof(char*) * (n_tokens + 1));
                tokens[n_tokens++] = token;

                token = nullptr;
                len = 0;
            }
        }
    }

    tokens = (char**)realloc(tokens, sizeof(char*) * (n_tokens + 1));
    tokens[n_tokens] = nullptr;
    return tokens;
}

void freeSplit(char** t){
    for (int i = 0; t[i] != nullptr; i++) {
        free(t[i]);
    }
    free(t);
}

bool SerialROS2::init(){
    this->pc.set_baud(baud_rate);
    this->pc.set_blocking(false);
    return true;
}

DataRecv SerialROS2::recv(){
    DataRecv data_recv;
    data_recv.num_recv = pc.read(&data_recv.data, MAXIMUM_BUFFER_SIZE);
    return data_recv;
}

// Buffered packet parser. New bytes are appended into `accum`; only
// complete packets terminated by 'd' or '\n' are dispatched. Partial
// reads stay in the buffer until the next call completes them.
void SerialROS2::recvVals(char sep){
    DataRecv res = this->recv();
    if (res.num_recv <= 0) return;

    int to_copy = res.num_recv;
    if (accum_len + to_copy > ACCUM_BUFFER_SIZE - 1) {
        // overflow guard: drop everything buffered so far rather than
        // emit a garbled half-packet
        accum_len = 0;
    }
    if (to_copy > ACCUM_BUFFER_SIZE - 1) to_copy = ACCUM_BUFFER_SIZE - 1;
    for (int i = 0; i < to_copy && accum_len < ACCUM_BUFFER_SIZE - 1; i++) {
        accum[accum_len++] = res.data[i];
    }
    accum[accum_len] = '\0';

    int scan = 0;
    while (scan < accum_len) {
        int term = -1;
        for (int i = scan; i < accum_len; i++) {
            if (accum[i] == 'd' || accum[i] == '\n') { term = i; break; }
        }
        if (term < 0) break;  // wait for more bytes

        accum[term] = '\0';
        char* pkt = &accum[scan];

        float* recvs = nullptr;
        int n = 0;
        char** out = split(sep, pkt);
        for (int i = 0; out[i] != nullptr; i++) {
            recvs = (float*)realloc(recvs, sizeof(float) * (i + 1));
            recvs[i] = atof(out[i]);
            n++;
        }
        freeSplit(out);

        if (n >= 2 && this->recvCallback) {
            this->recvCallback(recvs);
        }
        if (recvs) free(recvs);

        scan = term + 1;
    }

    if (scan > 0) {
        int remaining = accum_len - scan;
        if (remaining > 0) {
            memmove(accum, &accum[scan], remaining);
        }
        accum_len = remaining;
        accum[accum_len] = '\0';
    }
}

void SerialROS2::send(void* data_send, uint32_t size){
    pc.write(data_send, size);
}

void SerialROS2::attach(void (*func)(), chrono::milliseconds t=2000ms){
    send_timer.attach( callback(func), t);
}
