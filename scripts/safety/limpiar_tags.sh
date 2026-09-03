#!/bin/bash
cd /mnt/ssd_trabajo/hermes-agent
git tag | grep "^safety-" | sort -r | tail -n +101 | xargs -I{} git tag -d {}
