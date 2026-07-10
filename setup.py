import os
import platform
import shutil
import subprocess
import sys
import sysconfig
import tempfile

from setuptools import Extension, setup

HERE = os.path.dirname(__file__)


system = platform.system()

if system == "Darwin":
    ext = Extension(
        "sobornost._native",
        sources=["sobornost/_macos_utils.m"],
        extra_compile_args=["-ObjC"],
        extra_link_args=[
            "-framework", "Carbon",
            "-framework", "CoreGraphics",
            "-framework", "ApplicationServices",
            "-framework", "AppKit",
            "-framework", "Foundation",
            "-framework", "ScreenCaptureKit",
        ],
    )
elif system == "Linux":
    ext = Extension(
        "sobornost._native",
        sources=["sobornost/_linux_utils.c"],
        extra_compile_args=[],
        extra_link_args=[],
        libraries=["xcb", "xcb-ewmh", "xcb-damage", "xcb-keysyms"],
    )
else:
    print(f"ERROR: unsupported platform: {system}", file=sys.stderr)
    sys.exit(1)

setup_kwargs = dict(
    ext_modules=[ext],
    install_requires=["pillow"],
)

# py2app configuration — standalone .app for macOS
if system == "Darwin":
    icon_path = os.path.join(
        HERE, "packaging", "sobornost.app", "Contents", "Resources", "sobornost.icns",
    )
    if not os.path.exists(icon_path):
        icon_path = None

    # Work around py2app 0.28.x incompatibilities:
    #   1. install_requires is rejected — clear it before the check.
    #   2. zlib is built-in (no __file__) on Python 3.14+ — set
    #      __file__ to a dummy path and patch copy_file to skip
    #      non-existent sources so nothing gets copied.
    try:
        import zlib
        if not hasattr(zlib, "__file__"):
            zlib.__file__ = "/_builtin_/zlib"
    except ImportError:
        pass

    try:
        import py2app.build_app as _ba
        _orig_copy_file = _ba.py2app.copy_file

        def _patched_copy_file(self, src, dst, *a, **kw):
            if isinstance(src, str) and not os.path.exists(src):
                return
            return _orig_copy_file(self, src, dst, *a, **kw)

        _ba.py2app.copy_file = _patched_copy_file

        from py2app.build_app import py2app as _py2app_base

        class _py2app_compat(_py2app_base):  # noqa: N801
            def finalize_options(self):
                self.distribution.install_requires = None
                super().finalize_options()

            def run(self):
                super().run()
                self._bundle_tcltk()

            def _bundle_tcltk(self):
                from glob import glob
                dist_dir = self.dist_dir or "dist"
                apps = glob(os.path.join(dist_dir, "*.app"))
                if not apps:
                    return
                app_path = apps[0]
                bundle_lib = os.path.join(app_path, "Contents", "Resources", "lib")
                os.makedirs(bundle_lib, exist_ok=True)
                src_lib = sysconfig.get_config_var("LIBDIR")
                if not src_lib:
                    return
                for name in ("libtcl8.6.dylib", "libtk8.6.dylib"):
                    src = os.path.join(src_lib, name)
                    if os.path.exists(src):
                        shutil.copy2(src, bundle_lib)
                        print(f"  bundled {name}")
                for name in ("tcl8.6", "tk8.6"):
                    src = os.path.join(src_lib, name)
                    dst = os.path.join(bundle_lib, name)
                    if os.path.isdir(src) and not os.path.isdir(dst):
                        shutil.copytree(src, dst, symlinks=True)
                        print(f"  bundled {name}/")
                self._sign_app(app_path)

            def _sign_app(self, app_path):
                """Re-sign .app with a self-signed cert + hardened runtime
                entitlements, giving a stable identity that TCC remembers
                across rebuilds (no more repeated Screen Recording prompts)."""
                cert_name = "sobornost-dev"
                self._ensure_cert(cert_name)
                entitlements = os.path.join(HERE, "packaging", "entitlements.plist")
                subprocess.run([
                    "codesign", "--force", "--sign", cert_name,
                    "--options", "runtime",
                    "--entitlements", entitlements,
                    "--deep", app_path,
                ], check=True)
                print(f"  signed {os.path.basename(app_path)}")

            @staticmethod
            def _ensure_cert(cert_name):
                """Create a self-signed code signing certificate if needed."""
                tmp = os.path.join(tempfile.mkdtemp(), "cert_test")
                try:
                    with open(tmp, "w") as f:
                        f.write("x")
                    subprocess.run(
                        ["codesign", "-s", cert_name, tmp],
                        capture_output=True, check=True,
                    )
                    return
                except subprocess.CalledProcessError:
                    pass
                finally:
                    try:
                        os.remove(tmp)
                        os.rmdir(os.path.dirname(tmp))
                    except OSError:
                        pass
                d = tempfile.mkdtemp()
                try:
                    key = os.path.join(d, "key.pem")
                    req = os.path.join(d, "req.pem")
                    crt = os.path.join(d, "crt.pem")
                    p12 = os.path.join(d, "cert.p12")
                    conf = os.path.join(d, "cert.conf")
                    with open(conf, "w") as f:
                        f.write("[v3_req]\n")
                        f.write("basicConstraints=CA:FALSE\n")
                        f.write("keyUsage=critical,digitalSignature\n")
                        f.write("extendedKeyUsage=codeSigning\n")
                        f.write("subjectKeyIdentifier=hash\n")
                    subprocess.run(["openssl", "genrsa", "-out", key, "2048"],
                                   capture_output=True, check=True)
                    subprocess.run(["openssl", "req", "-new", "-key", key,
                                    "-out", req, "-subj", f"/CN={cert_name}"],
                                    capture_output=True, check=True)
                    subprocess.run(["openssl", "x509", "-req", "-days", "3650",
                                    "-in", req, "-signkey", key,
                                    "-extfile", conf, "-extensions", "v3_req",
                                    "-out", crt],
                                    capture_output=True, check=True)
                    subprocess.run(["openssl", "pkcs12", "-export",
                                   "-inkey", key, "-in", crt,
                                   "-out", p12, "-passout", "pass:"],
                                   capture_output=True, check=True)
                    subprocess.run(["security", "import", p12,
                                   "-k",
                                   os.path.expanduser(
                                       "~/Library/Keychains/login.keychain"
                                   ),
                                   "-P", "", "-T", "/usr/bin/codesign", "-A"],
                                   capture_output=True, check=True)
                    print(f"  created signing identity: {cert_name}")
                finally:
                    shutil.rmtree(d, ignore_errors=True)
        cmdclass = dict(setup_kwargs.get("cmdclass", {}), py2app=_py2app_compat)
        setup_kwargs["cmdclass"] = cmdclass
    except ImportError:
        pass

    setup_kwargs.update(
        app=[os.path.join(HERE, "sobornost", "__main__.py")],
        options={
            "py2app": {
                "argv_emulation": False,
                "packages": ["sobornost", "PIL"],
                "includes": ["tkinter"],
                "plist": {
                    "CFBundleName": "sobornost",
                    "CFBundleDisplayName": "sobornost",
                    "CFBundleIdentifier": "com.sobornost.app",
                    "CFBundleVersion": "0.1.0",
                    "CFBundleShortVersionString": "0.1.0",
                    "NSHighResolutionCapable": True,
                    "LSUIElement": False,
                },
            },
        },
    )
    if icon_path:
        setup_kwargs["options"]["py2app"]["iconfile"] = icon_path

setup(**setup_kwargs)

