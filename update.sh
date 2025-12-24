#!/bin/bash

git fetch
git pull
sudo systemctl restart nginx
sudo systemctl restart flaskapp
