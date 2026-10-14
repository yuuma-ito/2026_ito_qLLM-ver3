"""Linux fail-closed Landlock ABI>=3 + seccomp policy installed before imports.

No security claim for arbitrary native/kernel exploits. Never use this as a
portable subprocess fallback: unsupported hosts must refuse execution.
"""
import ctypes
import errno
import os
import platform
import resource

POLICY_VERSION = "linux_landlock_seccomp_v1"


def install(read_paths, write_paths, limits):
    if platform.machine() != "x86_64" or platform.system() != "Linux":
        raise RuntimeError("sandbox requires Linux x86_64")
    # Only stdlib is loaded at this point: pre-existing threads would escape
    # the Landlock ABI4 per-thread domain. Refuse instead of assuming safety.
    if len(os.listdir("/proc/self/task")) != 1:
        raise RuntimeError("sandbox must be installed before any threads")
    libc = ctypes.CDLL(None, use_errno=True)
    abi = libc.syscall(444, 0, 0, 1)
    if abi < 3:
        raise RuntimeError("Landlock ABI>=3 is required")
    mask = (1 << 15) - 1  # through REFER + TRUNCATE (ABI3)

    class Ruleset(ctypes.Structure):
        _fields_ = [("handled", ctypes.c_uint64)]

    class PathRule(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("allowed", ctypes.c_uint64), ("parent_fd", ctypes.c_int)]

    attributes = Ruleset(mask)
    fd = libc.syscall(444, ctypes.byref(attributes), ctypes.sizeof(attributes), 0)
    if fd < 0:
        raise OSError(ctypes.get_errno(), "Landlock create")
    try:
        for path, writable in [(p, p == "/dev/null") for p in read_paths] + [(p, True) for p in write_paths]:
            if not os.path.exists(path):
                continue
            pfd = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                access = (1 << 2) | ((1 << 3) if os.path.isdir(path) else 0)  # READ_FILE, READ_DIR
                if writable:
                    if os.path.isdir(path):
                        raise ValueError("writable directories are forbidden")
                    access = (1 << 1) | (1 << 2) | (1 << 14)
                rule = PathRule(access, pfd)
                if libc.syscall(445, fd, 1, ctypes.byref(rule), 0) < 0:
                    raise OSError(ctypes.get_errno(), "Landlock add")
            finally:
                os.close(pfd)
        if libc.prctl(38, 1, 0, 0, 0) != 0 or libc.syscall(446, fd, 0) != 0:
            raise OSError(ctypes.get_errno(), "Landlock restrict")
    finally:
        os.close(fd)

    sec = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    sec.seccomp_init.argtypes = [ctypes.c_uint32]
    sec.seccomp_init.restype = ctypes.c_void_p
    sec.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    sec.seccomp_syscall_resolve_name.restype = ctypes.c_int
    sec.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    sec.seccomp_load.argtypes = [ctypes.c_void_p]
    sec.seccomp_release.argtypes = [ctypes.c_void_p]
    ctx = sec.seccomp_init(0x7FFF0000)  # default allow; filesystem is Landlock
    if not ctx:
        raise RuntimeError("seccomp_init failed")
    denied = "socket socketpair connect bind listen accept accept4 sendto sendmsg recvfrom recvmsg execve execveat fork vfork ptrace process_vm_readv process_vm_writev pidfd_open pidfd_getfd pidfd_send_signal rt_sigqueueinfo rt_tgsigqueueinfo bpf userfaultfd io_uring_setup mount umount2 unshare setns pivot_root chroot open_by_handle_at kill tkill tgkill reboot kexec_load setpriority sched_setaffinity sched_setparam sched_setscheduler".split()
    try:
        for name in denied + ["clone3"]:
            syscall = sec.seccomp_syscall_resolve_name(name.encode())
            action = 0x00050000 | (errno.ENOSYS if name == "clone3" else errno.EPERM)
            if syscall < 0 or sec.seccomp_rule_add(ctx, action, syscall, 0) != 0:
                raise RuntimeError("seccomp rule failed: " + name)

        class Compare(ctypes.Structure):
            _fields_ = [("arg", ctypes.c_uint), ("op", ctypes.c_int), ("a", ctypes.c_uint64), ("b", ctypes.c_uint64)]

        # Permit pthread clone only; deny new processes. clone3 gets ENOSYS so
        # libc can fall back to clone, with the same inherited restrictions.
        sec.seccomp_rule_add_array.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint, ctypes.POINTER(Compare)]
        comparison = Compare(0, 7, 0x10000, 0)  # MASKED_EQ(flags, CLONE_THREAD, 0)
        if sec.seccomp_rule_add_array(ctx, 0x00050000 | errno.EPERM, sec.seccomp_syscall_resolve_name(b"clone"), 1, ctypes.byref(comparison)) != 0:
            raise RuntimeError("seccomp clone rule failed")
        other_process = Compare(0, 1, 0, 0)  # NE(pid, 0): only own prlimit permitted
        if sec.seccomp_rule_add_array(ctx, 0x00050000 | errno.EPERM, sec.seccomp_syscall_resolve_name(b"prlimit64"), 1, ctypes.byref(other_process)) != 0:
            raise RuntimeError("seccomp prlimit rule failed")
        if sec.seccomp_load(ctx) != 0:
            raise RuntimeError("seccomp load failed")
    finally:
        sec.seccomp_release(ctx)
    for key, value in ((resource.RLIMIT_CPU, int(limits["cpu_seconds"])),
                       (resource.RLIMIT_AS, int(limits["memory_bytes"])),
                       (resource.RLIMIT_FSIZE, int(limits["file_bytes"])),
                       (resource.RLIMIT_NOFILE, 64), (resource.RLIMIT_CORE, 0)):
        resource.setrlimit(key, (value, value + 1 if key == resource.RLIMIT_CPU else value))
    return {"policy": POLICY_VERSION, "landlock_abi": abi, "seccomp": True, "no_new_privs": True,
            "preexisting_threads": 1, "limits": limits}
