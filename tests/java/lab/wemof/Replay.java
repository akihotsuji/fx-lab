package lab.wemof;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
/** Test-only CSV runner; configuration passed by the Python test harness. */
public final class Replay {
    public static void main(String[] a) throws Exception {
        ObserverEngine.Config c = new ObserverEngine.Config(Integer.parseInt(a[3]), Double.parseDouble(a[4]),
            Double.parseDouble(a[5]),Double.parseDouble(a[6]),Long.parseLong(a[7]),Long.parseLong(a[8]),
            Double.parseDouble(a[9]),Double.parseDouble(a[10]),ObserverEngine.PriceModel.valueOf(a[11]));
        ObserverEngine engine = new ObserverEngine(c);
        List<Double> seed = new ArrayList<Double>();
        for (String line : Files.readAllLines(Paths.get(a[1]),StandardCharsets.UTF_8)) {
            if (!line.startsWith("bar_start_ms") && !line.trim().isEmpty()) seed.add(Double.parseDouble(line.split(",")[1]));
        }
        engine.seed(seed);
        try (BufferedReader in = Files.newBufferedReader(Paths.get(a[0]),StandardCharsets.UTF_8);
             BufferedWriter out = Files.newBufferedWriter(Paths.get(a[2]),StandardCharsets.UTF_8)) {
            out.write(ObserverEngine.Event.HEADER); out.newLine(); in.readLine();
            String line;
            while ((line=in.readLine())!=null) {
                String[] r=line.split(",");
                for (ObserverEngine.Event e : engine.onTick(Long.parseLong(r[0]),Double.parseDouble(r[1]),Double.parseDouble(r[2]))) {
                    out.write(e.csv()); out.newLine();
                }
            }
            for (ObserverEngine.Event e : engine.end()) { out.write(e.csv()); out.newLine(); }
        }
    }
}
