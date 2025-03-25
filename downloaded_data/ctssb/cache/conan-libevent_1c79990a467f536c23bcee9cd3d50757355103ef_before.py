from conans import ConanFile, ConfigureEnvironment
from conans.tools import download, untargz, check_sha1, replace_in_file
import os
import shutil

class LibeventConan(ConanFile):
    name = "libevent"
    version = "2.0.22"
    url = "https://github.com/theirix/conan-libevent"
    license = "https://github.com/libevent/libevent/blob/release-%s-stable/LICENSE" % version
    FOLDER_NAME = 'libevent-%s-stable' % version
    settings = "os", "compiler", "build_type", "arch"
    options = {"shared": [True, False],
               "with_openssl": [True, False],
               "disable_threads": [True, False]}
    default_options = "shared=False", "with_openssl=True", "disable_threads=False"


    def config(self):
        del self.settings.compiler.libcxx
        if self.options.with_openssl:
            self.requires.add("OpenSSL/1.0.2e@lasote/stable", private=False)
            self.options["OpenSSL"].shared = self.options.shared
        else:
            del self.requires["OpenSSL"]

    def source(self):
        tarball_name = self.FOLDER_NAME + '.tar.gz'
        download("https://github.com/libevent/libevent/releases/download/release-%s-stable/%s.tar.gz"
                 % (self.version, self.FOLDER_NAME), tarball_name)
        check_sha1(tarball_name, "a586882bc93a208318c70fc7077ed8fca9862864")
        untargz(tarball_name)
        os.unlink(tarball_name)

    def build(self):

        env = ConfigureEnvironment(self.deps_cpp_info, self.settings)

        if self.settings.os == "Linux" or self.settings.os == "Macos":

            env_line = env.command_line
            env_line_configure = env_line

            # Configure script creates conftest that cannot execute without shared openssl binaries.
            # Ways to solve the problem:
            # 1. set *LD_LIBRARY_PATH (works with Linux but does not work on OS X 10.11 with SIP)
            # 2. copying dylib's to the build directory (fortunately works on OS X)
            # 3. set rpath (dangerous)
            imported_libs = []
            if self.options.with_openssl and self.options.shared:
                if self.settings.os == "Macos":
                    imported_libs = os.listdir(self.deps_cpp_info['OpenSSL'].lib_paths[0])
                    for imported_lib in imported_libs:
                        shutil.copy(self.deps_cpp_info['OpenSSL'].lib_paths[0] + '/' + imported_lib, self.FOLDER_NAME)
                    self.output.warn("Copying OpenSSL libraries to fix conftest")
                if self.settings.os == "Linux":
                    env_line_configure += " LD_LIBRARY_PATH=" + ':'.join(self.deps_cpp_info.libdirs)

            # required to correctly find static libssl on Linux
            if self.options.with_openssl and self.settings.os == "Linux":
                env_line_configure += " OPENSSL_LIBADD=-ldl"

            # disable rpath build
            old_str = "-install_name \$rpath/"
            new_str = "-install_name "
            replace_in_file("%s/configure" % self.FOLDER_NAME, old_str, new_str)

            # compose configure options
            suffix = ''
            if not self.options.shared:
                suffix += " --disable-shared "
            if self.options.with_openssl:
                suffix += "--enable-openssl "
            else:
                suffix += "--disable-openssl "
            if self.options.disable_threads:
                suffix += "--disable-thread-support "

            cmd = 'cd %s && %s %s ./configure %s' % (self.FOLDER_NAME, env_line, env_line_configure, suffix)
            self.output.warn('Running: ' + cmd)
            self.run(cmd)

            cmd = 'cd %s && %s make' % (self.FOLDER_NAME, env_line)
            self.output.warn('Running: ' + cmd)
            self.run(cmd)

            # now clean imported libs
            if imported_libs:
                for imported_lib in imported_libs:
                    os.unlink(self.FOLDER_NAME + '/' + imported_lib)

    def package(self):
        self.copy("*.h", dst="include", src="%s/include" % (self.FOLDER_NAME))
        for header in ['evdns', 'event', 'evhttp', 'evrpc', 'evutil']:
            self.copy(header+'.h', dst="include", src="%s" % (self.FOLDER_NAME))
        if self.options.shared:
            if self.settings.os == "Macos":
                self.copy(pattern="*.dylib", dst="lib", keep_path=False)
            else:
                self.copy(pattern="*.so*", dst="lib", keep_path=False)
        else:
            self.copy(pattern="*.a", dst="lib", keep_path=False)

    def package_info(self):

        if self.settings.os == "Linux" or self.settings.os == "Macos":
            self.cpp_info.libs = ['event']
            if self.options.with_openssl:
                self.cpp_info.libs.extend(["event_openssl"])
        if self.settings.os == "Linux":
            self.cpp_info.libs.extend(["rt"])

