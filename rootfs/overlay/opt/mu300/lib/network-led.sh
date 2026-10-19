#!/bin/sh
# A selected, scoped CEREG?/C5GREG? snapshot. No AT ownership or timers here.
# CEREG AcT is field five, not the last field (reject cause/timers may follow).
# EPS can keep reporting LTE AcT=7 while the separate NR domain is registered.
mu300_network_led_state() {
    awk -F, '
        /^\+C(5G|E)REG:/ {
            family = ($0 ~ /^\+C5GREG:/) ? "nr" : "eps"
            stat = $2; act = $5
            gsub(/[ \t\r]/, "", stat); gsub(/[ \t\r]/, "", act)
            if (family == "nr" && stat ~ /^(0|2|3|4)$/) nr_absent = 1
            if (stat !~ /^(1|5)$/) next
            if (family == "nr") nr = 1
            else if (act ~ /^(11|12|13|15)$/) eps_nr = 1
            else if (act ~ /^(0|1|2|3|4|5|6|7|8|9|10)$/) eps = 1
            else eps_short = 1
        }
        END {
            if (nr || eps_nr) print "online-5g"
            else if (eps || (eps_short && nr_absent)) print "online-4g"
            else exit 1
        }'
}
