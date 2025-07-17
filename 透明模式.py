#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import struct
import base64
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
import getpass

TAIL_END = b"###END###"

def rotate_left(v, c):
    return ((v << c) & 0xffffffff) | (v >> (32 - c))

def quarter_round(state, a, b, c, d):
    state[a] = (state[a] + state[b]) & 0xffffffff
    state[d] ^= state[a]
    state[d] = rotate_left(state[d], 16)
    state[c] = (state[c] + state[d]) & 0xffffffff
    state[b] ^= state[c]
    state[b] = rotate_left(state[b], 12)
    state[a] = (state[a] + state[b]) & 0xffffffff
    state[d] ^= state[a]
    state[d] = rotate_left(state[d], 8)
    state[c] = (state[c] + state[d]) & 0xffffffff
    state[b] ^= state[c]
    state[b] = rotate_left(state[b], 7)

def chacha20_block(key, counter, nonce):
    if len(key) != 32 or len(nonce) != 12:
        raise ValueError("Key必须32字节，Nonce必须12字节")
    constants = b"expand 32-byte k"
    state_bytes = constants + key + struct.pack("<I", counter) + nonce
    state = list(struct.unpack("<16I", state_bytes))
    working = state[:]
    for _ in range(10):
        quarter_round(working, 0, 4, 8,12)
        quarter_round(working, 1, 5, 9,13)
        quarter_round(working, 2, 6,10,14)
        quarter_round(working, 3, 7,11,15)
        quarter_round(working, 0, 5,10,15)
        quarter_round(working, 1, 6,11,12)
        quarter_round(working, 2, 7, 8,13)
        quarter_round(working, 3, 4, 9,14)
    result = []
    for i in range(16):
        result.append((working[i] + state[i]) & 0xffffffff)
    return struct.pack("<16I", *result)

def chacha20_encrypt(key, nonce, counter, plaintext):
    out = bytearray(len(plaintext))
    block_count = (len(plaintext) + 63) // 64
    for i in range(block_count):
        keystream = chacha20_block(key, counter + i, nonce)
        for j in range(64):
            idx = i * 64 + j
            if idx >= len(plaintext):
                break
            out[idx] = plaintext[idx] ^ keystream[j]
    return bytes(out)

def poly1305_clamp(r):
    r_list = list(r)
    r_list[3] &= 15
    r_list[7] &= 15
    r_list[11] &= 15
    r_list[15] &= 15
    r_list[4] &= 252
    r_list[8] &= 252
    r_list[12] &= 252
    return bytes(r_list)

def poly1305_mac(msg, key):
    if len(key) != 32:
        raise ValueError("Poly1305密钥必须32字节")
    r = poly1305_clamp(key[:16])
    s = key[16:]
    p = (1 << 130) - 5
    # 转换r为整数
    r_num = 0
    for i in range(16):
        r_num |= r[i] << (8 * i)
    acc = 0
    # 每16字节分块累加计算
    offset = 0
    msg_len = len(msg)
    while offset < msg_len:
        block = msg[offset:offset+16]
        n = 0
        for i in range(len(block)):
            n |= block[i] << (8 * i)
        n += 1 << (8 * len(block))
        acc = (acc + n) % p
        acc = (acc * r_num) % p
        offset += 16
    s_num = 0
    for i in range(16):
        s_num |= s[i] << (8 * i)
    acc = (acc + s_num) % (1 << 128)
    # 输出16字节tag
    tag = bytearray(16)
    for i in range(16):
        tag[i] = (acc >> (8 * i)) & 0xff
    return bytes(tag)

def pad16(data):
    pad_len = (16 - (len(data) % 16)) % 16
    if pad_len == 0:
        return data
    return data + b'\x00' * pad_len

def poly1305_input(aad, ciphertext):
    result = pad16(aad)
    result += pad16(ciphertext)
    result += struct.pack("<Q", len(aad))
    result += struct.pack("<Q", len(ciphertext))
    return result

def chacha20poly1305_encrypt(key, plaintext, nonce, aad=b""):
    poly_key = chacha20_block(key, 0, nonce)[:32]
    ciphertext = chacha20_encrypt(key, nonce, 1, plaintext)
    auth_data = poly1305_input(aad, ciphertext)
    tag = poly1305_mac(auth_data, poly_key)
    return ciphertext, tag

def chacha20poly1305_decrypt(key, ciphertext, nonce, tag, aad=b""):
    poly_key = chacha20_block(key, 0, nonce)[:32]
    auth_data = poly1305_input(aad, ciphertext)
    expected_tag = poly1305_mac(auth_data, poly_key)
    if expected_tag != tag:
        raise ValueError("认证失败，标签不匹配")
    plaintext = chacha20_encrypt(key, nonce, 1, ciphertext)
    return plaintext

def encode_tail(nonce, tag):
    obj = {"nonce": base64.b64encode(nonce).decode("ascii"), "tag": base64.b64encode(tag).decode("ascii")}
    return json.dumps(obj, separators=(',', ':')).encode("utf-8") + TAIL_END

def decode_tail(filedata):
    idx = filedata.rfind(TAIL_END)
    if idx == -1:
        raise ValueError("未找到尾部标记")
    search_start = max(0, idx - 1024)
    for start in range(idx - 1, search_start - 1, -1):
        try:
            js = filedata[start:idx]
            obj = json.loads(js.decode("utf-8"))
            nonce = base64.b64decode(obj["nonce"])
            tag = base64.b64decode(obj["tag"])
            return nonce, tag, start
        except Exception:
            continue
    raise ValueError("尾部结构解析失败")

def backup_file_attrs(filename):
    try:
        st = os.stat(filename)
        return (st.st_atime, st.st_mtime), st.st_mode
    except Exception:
        return None, None

def restore_file_attrs(filename, times, mode):
    try:
        if times is not None:
            os.utime(filename, times=times)
        if mode is not None:
            os.chmod(filename, mode)
    except Exception:
        pass

def derive_key(password):
    salt = b"ChaCha20Poly1305Salt"
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000, 32)
    return key

def encrypt_file(filepath, key):
    try:
        f = open(filepath, "rb")
        plaintext = f.read()
        f.close()
    except Exception as e:
        print(f"[读取失败] {filepath} : {e}")
        return False
    nonce = os.urandom(12)
    ciphertext, tag = chacha20poly1305_encrypt(key, plaintext, nonce)
    times, mode = backup_file_attrs(filepath)
    try:
        f = open(filepath, "wb")
        f.write(ciphertext)
        f.write(encode_tail(nonce, tag))
        f.close()
        restore_file_attrs(filepath, times, mode)
        print(f"[加密成功] {filepath}")
        return True
    except Exception as e:
        print(f"[写入失败] {filepath} : {e}")
        return False

def decrypt_file(filepath, key):
    try:
        f = open(filepath, "rb")
        data = f.read()
        f.close()
    except Exception as e:
        print(f"[读取失败] {filepath} : {e}")
        return False
    try:
        nonce, tag, tail_start = decode_tail(data)
    except Exception as e:
        print(f"[尾部解析失败] {filepath} : {e}")
        return False
    ciphertext = data[:tail_start]
    try:
        plaintext = chacha20poly1305_decrypt(key, ciphertext, nonce, tag)
    except Exception as e:
        print(f"[认证失败] {filepath} : {e}")
        return False
    times, mode = backup_file_attrs(filepath)
    try:
        f = open(filepath, "wb")
        f.write(plaintext)
        f.close()
        restore_file_attrs(filepath, times, mode)
        print(f"[解密成功] {filepath}")
        return True
    except Exception as e:
        print(f"[写入失败] {filepath} : {e}")
        return False

def collect_files(path):
    files = []
    if os.path.isfile(path):
        files.append(path)
    elif os.path.isdir(path):
        for root, dirs, filenames in os.walk(path):
            for fn in filenames:
                files.append(os.path.join(root, fn))
    return files

def batch_process(files, key, mode, max_workers=4):
    if mode == "enc":
        func = encrypt_file
    else:
        func = decrypt_file
    success_files = []
    failed_files = []
    executor = ThreadPoolExecutor(max_workers=max_workers)
    futures = {}
    for f in files:
        future = executor.submit(func, f, key)
        futures[future] = f
    for future in as_completed(futures):
        try:
            result = future.result()
            if result:
                success_files.append(futures[future])
            else:
                failed_files.append(futures[future])
        except Exception:
            failed_files.append(futures[future])
    executor.shutdown(wait=True)
    return success_files, failed_files

def main():
    print("="*60)
    print("ChaCha20-Poly1305 文件批量加解密工具 (免费纯净版)")
    print("="*60)
    mode = ""
    while True:
        mode = input("操作模式 (enc=加密, dec=解密): ").strip().lower()
        if mode == "enc" or mode == "dec":
            break
        print("请输入 'enc' 或 'dec'")
    path = ""
    while True:
        path = input("输入文件或目录路径: ").strip()
        if os.path.exists(path):
            break
        print("路径不存在，请重新输入")
    threads = 4
    while True:
        t = input("并发线程数 (默认4): ").strip()
        if t == "":
            break
        if t.isdigit() and int(t) > 0:
            threads = int(t)
            break
        print("请输入正整数")
    password = getpass.getpass("请输入密码（用于密钥派生）: ")
    key = derive_key(password)
    files = collect_files(path)
    print(f"\n共找到 {len(files)} 个文件，开始{'加密' if mode=='enc' else '解密'}任务...\n")
    success_files, failed_files = batch_process(files, key, mode, threads)
    print("\n处理完成!")
    print(f"成功文件数: {len(success_files)}")
    print(f"失败文件数: {len(failed_files)}")
    if len(failed_files) > 0:
        print("失败文件列表:")
        for ff in failed_files:
            print(" " + ff)

if __name__=="__main__":
    main()
