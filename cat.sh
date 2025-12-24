#!/bin/zsh

show() {
  printf '\n$ %s\n' "$1"
  eval "$1"
}

show "ls"
show "tree static"
show "tree templates"
show "cat templates/index.html"
show "cat static/css/cover.css"
show "cat templates/base.html"
show "cat templates/index.html"
show "cat templates/about.html"
show "cat templates/comments.html"
show "cat templates/contacts.html"
show "cat app.py"
