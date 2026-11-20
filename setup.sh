#!/bin/sh
# يضبط اسم حسابك على GitHub في كل الملفات ويعيد بناء ipk.
# الاستخدام: ./setup.sh YourGitHubName
[ -z "$1" ] && { echo "usage: ./setup.sh GITHUB_USER"; exit 1; }
cd "$(dirname "$0")"
for f in README.md install.sh build_ipk.sh plugin/online_web_control.py docs/post.txt; do
  [ -f "$f" ] && sed -i "s/YOUR_USER/$1/g" "$f"
done
./build_ipk.sh
