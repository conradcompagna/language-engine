import subprocess, os

msvc_base = r'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools'
msvc_ver = '14.44.35207'
cuda_base = r'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.2'
win_sdk = '10.0.26100.0'
wk = r'C:\Program Files (x86)\Windows Kits\10'

env = os.environ.copy()
env['PATH'] = (
    msvc_base + r'\VC\Tools\MSVC\\' + msvc_ver + r'\bin\Hostx64\x64' + ';' +
    msvc_base + r'\Common7\IDE' + ';' +
    msvc_base + r'\Common7\Tools' + ';' +
    wk + r'\bin\\' + win_sdk + r'\x64' + ';' +
    cuda_base + r'\bin' + ';' +
    cuda_base + r'\libnvvp' + ';' +
    env['PATH']
)
env['INCLUDE'] = (
    msvc_base + r'\VC\Tools\MSVC\\' + msvc_ver + r'\include' + ';' +
    wk + r'\Include\\' + win_sdk + r'\ucrt' + ';' +
    wk + r'\Include\\' + win_sdk + r'\shared' + ';' +
    wk + r'\Include\\' + win_sdk + r'\um' + ';' +
    cuda_base + r'\include'
)
env['LIB'] = (
    msvc_base + r'\VC\Tools\MSVC\\' + msvc_ver + r'\lib\x64' + ';' +
    wk + r'\Lib\\' + win_sdk + r'\ucrt\x64' + ';' +
    wk + r'\Lib\\' + win_sdk + r'\um\x64' + ';' +
    cuda_base + r'\lib\x64'
)
env['CMAKE_ARGS'] = '-DGGML_CUDA=on -DCMAKE_CUDA_COMPILER="' + cuda_base + r'\bin\nvcc.exe" -G "NMake Makefiles" -DCMAKE_CUDA_ARCHITECTURES=89'
env['CUDACXX'] = cuda_base + r'\bin\nvcc.exe'

print('nvcc:', env['CUDACXX'])
print('CMAKE_ARGS:', env['CMAKE_ARGS'])

import sys
result = subprocess.run(
    ['pip', 'install', 'llama-cpp-python', '--upgrade', '--force-reinstall', '--no-cache-dir', '-v'],
    env=env,
    shell=False,
    stdout=open('C:/Users/conra/Desktop/universal - js hybrid/experiment/build_log.txt', 'w'),
    stderr=subprocess.STDOUT
)
print('Exit code:', result.returncode)
