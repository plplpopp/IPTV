name: Update IPTV

on:
  schedule:
    - cron: '0 18 * * *'
  workflow_dispatch:
  push:
    branches: [ main, master ]

# 关键：声明写入权限
permissions:
  contents: write

jobs:
  update-iptv:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    
    steps:
    - name: Checkout repository
      uses: actions/checkout@v4
      with:
        # 使用默认的GITHUB_TOKEN，具有写入权限
        token: ${{ secrets.GITHUB_TOKEN }}
        
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
        
    - name: Install dependencies
      run: |
        pip install requests
        
    - name: Run IPTV collector
      run: |
        python iptv.py
        
    - name: Check for changes
      id: check-changes
      run: |
        git config --local user.name "github-actions[bot]"
        git config --local user.email "github-actions[bot]@users.noreply.github.com"
        git add -A
        if git diff --staged --quiet; then
          echo "changes=false" >> $GITHUB_OUTPUT
        else
          echo "changes=true" >> $GITHUB_OUTPUT
        fi
        
    - name: Commit and push changes
      if: steps.check-changes.outputs.changes == 'true'
      run: |
        git commit -m "🤖 Auto-update IPTV channels - $(date +'%Y-%m-%d %H:%M')"
        git push
        
    - name: Upload IPTV files as artifact
      uses: actions/upload-artifact@v4
      with:
        name: iptv-channels
        path: |
          iptv.txt
          iptv.m3u
          discovered_servers.txt
        retention-days: 7
