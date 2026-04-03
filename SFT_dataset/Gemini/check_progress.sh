#!/bin/bash
# Quick progress checker for SFT generation
# Usage: bash check_progress.sh

echo "═══════════════════════════════════════════════════"
echo "  FoodmoleGPT SFT Generation — Progress Report"
echo "═══════════════════════════════════════════════════"
echo ""

DIR="$(dirname "$0")/output"

for src in openalex pubmed; do
    FILE="$DIR/${src}.jsonl"
    PROG="$DIR/${src}_progress.json"
    if [ -f "$FILE" ]; then
        PAIRS=$(wc -l < "$FILE" | tr -d ' ')
        ARTICLES=$(python3 -c "import json; print(len(json.load(open('$PROG'))))" 2>/dev/null || echo "?")
        echo "  $src:"
        echo "    Articles processed: $ARTICLES / 10,000"
        echo "    QA pairs generated: $PAIRS / 50,000"
        echo "    Progress: $(python3 -c "print(f'{$PAIRS/50000*100:.1f}%')" 2>/dev/null)"
        echo ""
    fi
done

# Check if processes are still running
RUNNING=$(ps aux | grep "generate_sft.py" | grep -v grep | wc -l | tr -d ' ')
echo "  Active processes: $RUNNING"
echo ""

# Latest log entries
for src in openalex pubmed; do
    LOG=$(ls -t "$DIR/../logs/generate_${src}_"*.log 2>/dev/null | head -1)
    if [ -n "$LOG" ]; then
        LAST=$(grep "Progress:" "$LOG" | tail -1)
        if [ -n "$LAST" ]; then
            echo "  $src latest: $LAST"
        fi
    fi
done
echo ""
echo "═══════════════════════════════════════════════════"
