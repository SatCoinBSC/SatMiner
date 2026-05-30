from setuptools import setup, Extension
import platform

if platform.system() == 'Windows':
    # MSVC: /O2 最大速度, /GL 全程序优化
    extra_args = ['/O2', '/GL']
    link_args = ['/LTCG']
else:
    # GCC/Clang: -O3 + 针对当前CPU
    extra_args = ['-O3', '-march=native', '-funroll-loops']
    link_args = []

module = Extension('keccak_pow',
                  sources=['keccak_pow.c'],
                  extra_compile_args=extra_args,
                  extra_link_args=link_args)

setup(name='KeccakPow',
      version='1.1',
      description='Keccak-256 PoW C acceleration for Satoshi Miner',
      ext_modules=[module])
