import os, stat

temp_dir = "/tmp"
    
def claim_process(chroot, repo):

    label = chroot + "-" + repo
    
    # Try to create a file.
    path = os.path.join(temp_dir, label)
    try:
        os.mknod(path, 0644, stat.S_IFREG)

    except OSError:
        return None
    
    return path

def output_paths(path):

    stdout_path = path + ".stdout"
    stderr_path = path + ".stderr"
    result_path = path + ".result"

    return stdout_path, stderr_path, result_path

def update_process(path, pid):

    open(path, "w").write(str(pid))

def remove_lockfile(path):

    os.remove(path)

def status(chroot, repo):

    label = chroot + "-" + repo
    path = os.path.join(temp_dir, label)
    stdout_path, stderr_path, result_path = output_paths(path)

    if os.path.exists(path):
        if os.path.exists(result_path):
            result = open(result_path).read()
            if result == "0":
                return '<span style="success">Built</span>'
            else:
                return '<span style="failure">Failed</span>'
        else:
            return "Building"
    else:
        return ""
