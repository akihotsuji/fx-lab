package lab.wemof;

import java.util.*;

/** Deterministic quote observer. Never submits orders. Prices are USDJPY. */
public final class ObserverEngine {
    public static final long BAR_MS = 300_000L;
    public static final double PIP = 0.01, EPS = 1e-6;
    public enum PriceModel { BID_REFERENCE, BID_ASK }
    public static final class Config {
        public final int length;
        public final double sigma, targetPips, stopPips, additionalCostPips, maxSpreadPips;
        public final long watchMs, maxGapMs;
        public final PriceModel model;
        public Config(int length, double sigma, double target, double stop, long watchMs,
                      long maxGapMs, double additionalCost, double maxSpread, PriceModel model) {
            if (length < 2 || !finite(sigma) || sigma <= 0 || length - 1 <= sigma * sigma
                || !finite(target) || target <= 0 || !finite(stop) || stop <= 0
                || watchMs <= 0 || watchMs > 900_000 || maxGapMs <= 0
                || !finite(additionalCost) || additionalCost < 0
                || !finite(maxSpread) || maxSpread < 0 || model == null)
                throw new IllegalArgumentException("Invalid observer configuration");
            this.length = length; this.sigma = sigma; targetPips = target; stopPips = stop;
            this.watchMs = watchMs; this.maxGapMs = maxGapMs;
            additionalCostPips = additionalCost; maxSpreadPips = maxSpread; this.model = model;
        }
    }
    public static final class Event {
        public final String type, outcome, model;
        public final long id, timeMs, entryMs;
        public final int direction;
        public final double bid, ask, reference, upper, lower, spreadPips, mae, mfe;
        public final Double netPips;
        Event(String type, String outcome, long id, long time, long entryMs, int direction,
              double bid, double ask, double reference, double upper, double lower,
              double spread, double mae, double mfe, Double net, PriceModel model) {
            this.type = type; this.outcome = outcome; this.id = id; timeMs = time;
            this.entryMs = entryMs; this.direction = direction; this.bid = bid; this.ask = ask;
            this.reference = reference; this.upper = upper; this.lower = lower;
            spreadPips = spread; this.mae = mae; this.mfe = mfe; netPips = net; this.model = model.name();
        }
        public static final String HEADER = "type,outcome,id,time_ms,entry_ms,direction,bid,ask,reference,upper,lower,entry_spread_pips,mae_pips,mfe_pips,net_pips,elapsed_s,model";
        static String num(double x) { return finite(x) ? String.format(Locale.ROOT, "%.9f", x) : ""; }
        public String csv() {
            return type + "," + outcome + "," + id + "," + timeMs + "," + entryMs + "," + direction
                + "," + num(bid) + "," + num(ask) + "," + num(reference) + "," + num(upper)
                + "," + num(lower) + "," + num(spreadPips) + "," + num(mae) + "," + num(mfe)
                + "," + (netPips == null ? "" : num(netPips)) + ","
                + (entryMs < 0 ? "" : num(Math.max(0, timeMs - entryMs) / 1000.0)) + "," + model;
        }
    }
    private static final class Position {
        final long id, entryMs;
        final int direction;
        final double reference, upper, lower, spread;
        double mae, mfe;
        Position(long id, long time, int d, double ref, double up, double low, double spread, double initialMae) {
            this.id = id; entryMs = time; direction = d; reference = ref;
            upper = up; lower = low; this.spread = spread; mae = initialMae;
        }
    }
    private final Config config;
    private final Deque<Double> closes = new ArrayDeque<Double>();
    private final List<Position> active = new ArrayList<Position>();
    private long bucket = -1, previousTime = -1, nextId = 0;
    private double previousBid, upper = Double.NaN, lower = Double.NaN;
    private boolean used = false, dropFirstClose = true;
    private long contacts, skipped, completed, tp, sl, timeouts, interrupted, invalid;
    private double knownNet;
    public ObserverEngine(Config config) { this.config = config; }
    static boolean finite(double x) { return !Double.isNaN(x) && !Double.isInfinite(x); }
    /** Called once before the first quote. Only completed closes preceding that quote may be supplied. */
    public void seed(List<Double> completedCloses) {
        if (previousTime >= 0) throw new IllegalStateException("Seed must precede first quote");
        closes.clear();
        for (double x : completedCloses) {
            if (!finite(x) || x <= 0) throw new IllegalArgumentException("Invalid seed close");
            appendClose(x);
        }
        dropFirstClose = closes.size() != config.length - 1;
    }
    private void appendClose(double x) {
        closes.addLast(x);
        while (closes.size() > config.length - 1) closes.removeFirst();
    }
    private void boundary() {
        upper = lower = Double.NaN;
        if (closes.size() != config.length - 1) return;
        double mean = 0, variance = 0;
        for (double x : closes) mean += x;
        mean /= closes.size();
        for (double x : closes) variance += (x - mean) * (x - mean) / closes.size();
        if (variance <= 0) return;
        double radius = config.sigma * Math.sqrt(config.length * variance / (config.length - 1 - config.sigma * config.sigma));
        upper = mean + radius; lower = mean - radius;
    }
    public List<Event> onTick(long time, double bid, double ask) {
        List<Event> events = new ArrayList<Event>();
        if (time < 0 || !finite(bid) || !finite(ask) || bid <= 0 || ask < bid) {
            invalid++; events.add(diagnostic("INVALID_QUOTE", time, bid, ask)); return events;
        }
        if (previousTime >= 0 && time < previousTime) {
            invalid++; events.add(diagnostic("OUT_OF_ORDER", time, bid, ask)); return events;
        }
        boolean gap = previousTime >= 0 && time - previousTime > config.maxGapMs;
        for (Iterator<Position> it = active.iterator(); it.hasNext();) {
            Position p = it.next();
            double exit = config.model == PriceModel.BID_REFERENCE || p.direction == 1 ? bid : ask;
            double move = (exit - p.reference) * p.direction / PIP;
            String code = null;
            if (gap) code = "GAP";
            else {
                p.mae = Math.max(p.mae, Math.max(0, -move)); p.mfe = Math.max(p.mfe, Math.max(0, move));
                if (time - p.entryMs >= config.watchMs) code = "TIME";
                else if (move >= config.targetPips - EPS) code = "TP";
                else if (move <= -config.stopPips + EPS) code = "SL";
            }
            if (code != null) { events.add(finish(p, time, bid, ask, code, move)); it.remove(); }
        }
        long nextBucket = time / BAR_MS * BAR_MS;
        if (nextBucket != bucket) {
            if (bucket >= 0 && !dropFirstClose) appendClose(previousBid);
            else if (bucket >= 0) dropFirstClose = false;
            // Count observed market bars, including a previous session; never invent flat missing bars.
            bucket = nextBucket; used = false; boundary();
        }
        int d = finite(upper) && bid >= upper ? -1 : finite(lower) && bid <= lower ? 1 : 0;
        if (!used && d != 0) {
            used = true; contacts++; long id = ++nextId;
            double spread = (ask - bid) / PIP;
            double ref = config.model == PriceModel.BID_REFERENCE || d == -1 ? bid : ask;
            if (config.maxSpreadPips > 0 && spread > config.maxSpreadPips + EPS) {
                skipped++;
                events.add(new Event("SKIP", "SPREAD", id, time, time, d, bid, ask, ref,
                    upper, lower, spread, 0, 0, null, config.model));
            } else {
                double mae = config.model == PriceModel.BID_ASK ? spread : 0;
                Position p = new Position(id, time, d, ref, upper, lower, spread, mae);
                events.add(new Event("TOUCH", "", id, time, time, d, bid, ask, ref, upper, lower,
                    spread, mae, 0, null, config.model));
                if (mae >= config.stopPips - EPS) events.add(finish(p, time, bid, ask, "SL", -mae));
                else active.add(p);
            }
        }
        previousTime = time; previousBid = bid;
        return events;
    }
    private Event diagnostic(String code, long time, double bid, double ask) {
        return new Event("QUALITY", code, 0, time, -1, 0, bid, ask, Double.NaN,
            upper, lower, Double.NaN, Double.NaN, Double.NaN, null, config.model);
    }
    private Event finish(Position p, long time, double bid, double ask, String code, double move) {
        completed++;
        Double net = "GAP".equals(code) || "END".equals(code) ? null : move - config.additionalCostPips;
        if (net != null) knownNet += net;
        if ("TP".equals(code)) tp++;
        else if ("SL".equals(code)) sl++;
        else if ("TIME".equals(code)) timeouts++;
        else interrupted++;
        return new Event("RESULT", code, p.id, time, p.entryMs, p.direction, bid, ask, p.reference,
            p.upper, p.lower, p.spread, p.mae, p.mfe, net, config.model);
    }
    public List<Event> end() {
        List<Event> events = new ArrayList<Event>();
        for (Position p : active) events.add(finish(p, previousTime, previousBid, Double.NaN, "END", 0));
        active.clear(); return events;
    }
    public double upper() { return upper; }
    public double lower() { return lower; }
    public String summary() {
        return String.format(Locale.ROOT, "contacts=%d skipped=%d active=%d TP=%d SL=%d TIME=%d unknown=%d invalid=%d known_net_pips=%.3f",
            contacts, skipped, active.size(), tp, sl, timeouts, interrupted, invalid, knownNet);
    }
}
