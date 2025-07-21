#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import struct
import secrets
from concurrent.futures import ThreadPoolExecutor, as_completed

# ======= ChaCha20-Poly1305 零依赖实现 =======

def rotl32(v, c):
    return ((v << c) & 0xffffffff) | (v >> (32 - c))           # 左循环移位 32 位

def quarter_round(a, b, c, d):
    # 对 (a,b,c,d) 做一次 quarter round，用于混淆状态
    a = (a + b) & 0xffffffff; d ^= a; d = rotl32(d, 16)         # 第 1 步： a ← a + b; d ← (d ⊕ a) <<< 16
    c = (c + d) & 0xffffffff; b ^= c; b = rotl32(b, 12)         # 第 2 步： c ← c + d; b ← (b ⊕ c) <<< 12
    a = (a + b) & 0xffffffff; d ^= a; d = rotl32(d, 8)          # 第 3 步： a ← a + b; d ← (d ⊕ a) <<< 8
    c = (c + d) & 0xffffffff; b ^= c; b = rotl32(b, 7)          # 第 4 步： c ← c + d; b ← (b ⊕ c) <<< 7
    return a, b, c, d                                         # 返回新的四元组

def chacha20_block(key, counter, nonce):
    const = b"expa" b"nd 3" b"2-by" b"te k"                     # 固定常量 "expand 32-byte k"
    s0, s1, s2, s3 = struct.unpack("<4I", const)               # 4 个 32-bit 常量
    k0, k1, k2, k3, k4, k5, k6, k7 = struct.unpack("<8I", key)  # 8 个 32-bit 密钥字
    n0, n1, n2 = struct.unpack("<3I", nonce)                   # 3 个 32-bit 随机数（nonce）
    # 初始化 16 个 state：4 常量 | 8 密钥字 | 1 计数器 | 3 Nonce
    state = [s0, s1, s2, s3, k0, k1, k2, k3, k4, k5, k6, k7, counter, n0, n1, n2]
    w = state.copy()                                           # 工作副本

    for _ in range(10):                                        # 共 20 轮（10 次 column+diagonal）
        # column rounds
        w[0], w[4], w[8],  w[12] = quarter_round(w[0], w[4], w[8],  w[12])
        w[1], w[5], w[9],  w[13] = quarter_round(w[1], w[5], w[9],  w[13])
        w[2], w[6], w[10], w[14] = quarter_round(w[2], w[6], w[10], w[14])
        w[3], w[7], w[11], w[15] = quarter_round(w[3], w[7], w[11], w[15])
        # diagonal rounds
        w[0], w[5], w[10], w[15] = quarter_round(w[0], w[5], w[10], w[15])
        w[1], w[6], w[11], w[12] = quarter_round(w[1], w[6], w[11], w[12])
        w[2], w[7], w[8],  w[13] = quarter_round(w[2], w[7], w[8],  w[13])
        w[3], w[4], w[9],  w[14] = quarter_round(w[3], w[4], w[9],  w[14])

    # 把工作状态加回原始 state，得到最终输出
    out = [(w[i] + state[i]) & 0xffffffff for i in range(16)]
    return struct.pack("<16I", *out)                           # 打包成 64 字节

def chacha20_xor(key, nonce, counter, data):
    res = bytearray(len(data))                                 # 输出缓冲
    i = 0
    while i < len(data):
        block = chacha20_block(key, counter, nonce)            # 生成下一 64 字节 keystream
        length = min(64, len(data) - i)
        for j in range(length):
            res[i + j] = data[i + j] ^ block[j]                # 明文 ⊕ keystream = 密文
        i += length
        counter += 1                                           # 块计数器递增
    return bytes(res)

def poly1305_mac(one_time_key, msg):
    # Poly1305 计算：输入一次性密钥 otk 和消息，输出 16 字节 tag
    r = bytearray(one_time_key[:16])                           # r 参数
    s = one_time_key[16:]                                      # s 参数
    # 裁剪 r 的高位，以满足 Poly1305 规范
    r[3]  &= 15; r[7]  &= 15; r[11] &= 15; r[15] &= 15
    r[4]  &= 252; r[8]  &= 252; r[12] &= 252
    r_num = int.from_bytes(r, "little")
    s_num = int.from_bytes(s, "little")
    p = (1 << 130) - 5                                         # 模数
    acc = 0
    i = 0
    # 对消息分块（16 字节一块），每块追加一个 0x01，再累加并乘 r mod p
    while i < len(msg):
        chunk = msg[i:i+16]
        n = int.from_bytes(chunk + b"\x01", "little")
        acc = (acc + n) * r_num % p
        i += 16
    tag = (acc + s_num) & ((1 << 128) - 1)                     # 最后加 s，并截断到 128 位
    return tag.to_bytes(16, "little")

def equal_ct(a, b):
    # 常量时间比较，防止泄露长度信息
    if len(a) != len(b):
        return False
    r = 0
    for x, y in zip(a, b):
        r |= x ^ y
    return r == 0

def aead_encrypt(key, data):
    nonce = secrets.token_bytes(12)                            # 随机 12 字节 nonce
    otk = chacha20_block(key, 0, nonce)[:32]                   # otk: 用 counter=0 生成一次性 Poly1305 密钥
    ct = chacha20_xor(key, nonce, 1, data)                     # 从 counter=1 开始对明文加密
    # 构造 Poly1305 输入：密文 || 填充0到16字节对齐 || 8字节AAD长度(0) || 8字节密文长度
    pad = (16 - (len(ct) % 16)) % 16
    mac_input = ct + b"\x00" * pad + (0).to_bytes(8, "little") + len(ct).to_bytes(8, "little")
    tag = poly1305_mac(otk, mac_input)                         # 计算 tag
    return nonce + ct + tag                                    # 输出格式：nonce||密文||tag

def aead_decrypt(key, blob):
    if len(blob) < 12 + 16:
        raise ValueError("文件过短，无法解密")                   # blob长度至少要有 nonce(12) + tag(16)
    nonce = blob[:12]                                          # 拆分 nonce
    tag   = blob[-16:]                                         # 拆分 tag
    ct    = blob[12:-16]                                       # 拆分密文
    otk = chacha20_block(key, 0, nonce)[:32]                   # 重现一次性 key
    # 同加密端构造 Poly1305 输入，并验证 tag
    pad = (16 - (len(ct) % 16)) % 16
    mac_input = ct + b"\x00" * pad + (0).to_bytes(8, "little") + len(ct).to_bytes(8, "little")
    expect = poly1305_mac(otk, mac_input)
    if not equal_ct(expect, tag):
        raise ValueError("Poly1305 Tag 校验失败")               # 校验失败不解密
    return chacha20_xor(key, nonce, 1, ct)                     # 校验通过，返回解密明文

# ======= 文件遍历与多线程处理 =======

def process_file(path, key, mode):
    try:
        with open(path, "rb") as f:
            data = f.read()                                    # 读入整个文件
        if mode == "enc":
            out = aead_encrypt(key, data)                      # 加密
        else:
            out = aead_decrypt(key, data)                      # 解密
        with open(path, "wb") as f:
            f.write(out)                                       # 覆盖写回文件
        return None                                             # 无错误
    except Exception as e:
        return str(e)                                          # 返回异常消息

def gather_files(root):
    result = []
    for base, _, files in os.walk(root):                      # 递归遍历目录
        for fn in files:
            result.append(os.path.join(base, fn))             # 收集所有文件路径
    return result

# ======= 主流程 =======

def main():
    mode = ""
    while mode not in ("enc", "dec"):
        mode = input("请选择模式 enc(加密) 或 dec(解密)：").strip().lower()
    root = input("请输入要处理的目录路径：").strip()
    if not os.path.isdir(root):
        print("目录不存在，退出。")
        return
    key_hex = input("请输入32字节十六进制密钥：").strip()
    try:
        key = bytes.fromhex(key_hex)                          # hex → bytes
    except:
        print("密钥格式错误，退出。")
        return
    if len(key) != 32:
        print("密钥长度必须正好32字节（64个十六进制字符），退出。")
        return
    try:
        threads = int(input("请输入并发线程数（例如4）：").strip())
        if threads < 1:
            raise ValueError()
    except:
        print("线程数输入不合法，退出。")
        return

    files = gather_files(root)
    if not files:
        print("目录下没有任何文件，退出。")
        return

    errors = []
    print(f"开始{ '加密' if mode=='enc' else '解密' }，共发现{len(files)}个文件，使用{threads}线程并行处理。")

    with ThreadPoolExecutor(max_workers=threads) as exe:
        futures = {}
        for path in files:
            fut = exe.submit(process_file, path, key, mode)    # 提交每个文件的处理任务
            futures[fut] = path
        for fut in as_completed(futures):
            err = fut.result()                                 # 等待并获取结果
            if err:
                errors.append((futures[fut], err))             # 收集出错文件

    if errors:
        print("\n以下文件处理失败：", file=sys.stderr)
        for pth, msg in errors:
            print(f"{pth} 失败原因：{msg}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"所有文件{ '加密' if mode=='enc' else '解密' }完成。")

if __name__ == "__main__":
    main()                                                      # 程序入口
