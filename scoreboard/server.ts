import Debug from "debug"
import express from "express"
import { readdirSync, readFileSync, writeFileSync } from "fs"
import serveStatic from "serve-static"
import ws from "ws"

// @ts-ignore - module is messed up
import { SerialPort } from "serialport"
// @ts-ignore - module is messed up
import { ReadlineParser } from "@serialport/parser-readline"

//#region App setup

const debug = Debug("server")
debug.enabled = true

const app = express()
app.use(serveStatic("public"))
app.use(express.json())
app.use(express.urlencoded({ extended: true }))

const webServer = app.listen(4000, () => {
  debug("Server is running on http://localhost:4000")
})

const sockets = new Set<ws>()

const wsServer = new ws.Server({ noServer: true })
wsServer.on("connection", (socket) => {
  sockets.add(socket)
  debug(`Connected: ${sockets.size} scoreboards connected`)
  socket.on("close", () => {
    sockets.delete(socket)
    debug(`Disconnected: ${sockets.size} scoreboards connected`)
  })
})

webServer.on("upgrade", (request, socket, head) => {
  wsServer.handleUpgrade(request, socket, head, (socket) => {
    wsServer.emit("connection", socket, request)
  })
})

const devicePath = readdirSync("/dev")
  .map((p) => "/dev/" + p)
  .find(
    (p: string) =>
      p.startsWith("/dev/tty.usbmodem") || p.startsWith("/dev/tty.usbserial"),
  )
debug(`Device path: ${devicePath}`)

let port: SerialPort | null = null
let parser: ReadlineParser | null = null

if (devicePath) {
  port = new SerialPort({ path: devicePath, baudRate: 115200 })
  parser = port.pipe(new ReadlineParser({ delimiter: "\n" }))

  parser.on("data", (data: string) => {
    // The relay sends an object like {"host":"...", "message":"..."}
    let host, message
    try {
      const obj = JSON.parse(data)
      if (obj.host && obj.message) {
        host = obj.host
        message = obj.message
      } else {
        // debug(`Ignored serial data: ${JSON.stringify(obj)}`)
        return
      }
    } catch (err) {
      debug(`Ignored serial data: ${data}`)
      return
    }
    receiveTargetEvent(host, message)
  })

  port.on("error", (err: any) => {
    console.error("Error:", err)
    process.exit(1)
  })
}

const broadcast = (data: {
  state: string
  gameLength: number
  difficulty: string
  respawnDelayMin: number
  respawnDelayMax: number
  lifetime: number
  regularHealth: number
  bossHealth: number
}) => {
  port?.write(
    JSON.stringify({
      state,
      game_length: gameLength,
      difficulty,
      respawn_delay_min: respawnDelayMin,
      respawn_delay_max: respawnDelayMax,
      target_lifetime: lifetime,
      regular_target_health: regularHealth,
      boss_target_health: bossHealth,
    }) + "\n",
  )
}

//#endregion

//#region Game logic

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

type State = "idle" | "ready" | "game" | "end" | "test"

let state: State = "idle"
let difficulty: "easy" | "hard" | "wand" = "easy"
let score = 0
let gameLength = 30
let respawnDelayMin = 3000
let respawnDelayMax = 7000
let lifetime = 4000
let regularHealth = 1
let bossHealth = 3
let secondsLeft = 60
const seenEvents = new Set<string>() // Set of ip address + "|" + millis()
const nodes: Record<
  string,
  { version: string; state: string; millis: number }
> = {}

enum ScoreboardEvent {
  RegularDeath = "regular-death",
  BossDeath = "boss-death",
  BossAppear = "boss-appear",
}

enum TargetEvent {
  Idle = "idle",
  RegularDeath = "regular-death",
  BossDeath = "boss-death",
  BossAppear = "boss-appear",
}

const updateTargets = async () => {
  broadcast({
    state,
    difficulty,
    gameLength,
    respawnDelayMin,
    respawnDelayMax,
    lifetime,
    regularHealth,
    bossHealth,
  })
}

const updateScoreboard = () => {
  const message = JSON.stringify({
    state,
    difficulty,
    score,
    gameLength,
    respawnDelayMin,
    respawnDelayMax,
    lifetime,
    regularHealth,
    bossHealth,
    secondsLeft,
    stats: readStats(),
    nodes,
  })
  // debug("Sending to scoreboard: " + message)
  sockets.forEach((socket) => {
    socket.send(message)
  })
}

const sendScoreboardEvent = (event: ScoreboardEvent) => {
  const message = JSON.stringify({ event })
  debug("Sending to scoreboard: " + message)
  sockets.forEach((socket) => {
    socket.send(message)
  })
}

const receiveTargetEvent = (host: string, obj: any) => {
  if (typeof obj !== "object") return
  const { event, millis, version, state: objState } = obj

  if (objState) {
    debug(
      `Received state: ${host} version=${version} state=${objState} millis=${millis}`,
    )
    nodes[host] = { version, state, millis }
    return
  }

  if (!event || !millis) {
    debug("Invalid event in receiveTargetEvent: " + JSON.stringify(obj))
    return
  }

  if (seenEvents.has(host + "|" + millis)) {
    debug("Event already seen: " + host + "|" + millis)
    return
  }
  seenEvents.add(host + "|" + millis)

  debug(`Received event: ${host} ${event} ${millis}`)

  switch (event) {
    case TargetEvent.RegularDeath:
      if (state === "game" || state === "test") {
        score += 100
        sendScoreboardEvent(ScoreboardEvent.RegularDeath)
      }
      break
    case TargetEvent.BossDeath:
      if (state === "game" || state === "test") {
        score += 500
        sendScoreboardEvent(ScoreboardEvent.BossDeath)
      }
      break
    case TargetEvent.BossAppear:
      if (state === "game" || state === "test") {
        sendScoreboardEvent(ScoreboardEvent.BossAppear)
      }
      break
  }

  updateScoreboard()
}

setInterval(updateScoreboard, 1000)
setInterval(updateTargets, 1000)

type Stats = {
  highScore: number
  playCount: number
}

const readStats = (): Stats => {
  try {
    const stats = readFileSync("stats.json", "utf8")
    return JSON.parse(stats)
  } catch (err) {
    return { highScore: 0, playCount: 0 }
  }
}

const writeStats = (stats: Stats) => {
  writeFileSync("stats.json", JSON.stringify(stats), "utf8")
}

app.get("/c/menu", async (req, res) => {
  state = "idle"
  updateTargets()
  updateScoreboard()
  res.redirect("/admin.html")
})

app.get("/c/new", async (req, res) => {
  if (req.query.d === "wand") {
    gameLength = 30
    difficulty = "wand"
    lifetime = 7000
    bossHealth = 1
    regularHealth = 1
    respawnDelayMin = 1 * 1000
    respawnDelayMax = 4 * 1000
  } else if (req.query.d === "hard") {
    gameLength = 30
    difficulty = "hard"
    lifetime = 3000
    bossHealth = 5
    regularHealth = 3
    respawnDelayMin = 1 * 1000
    respawnDelayMax = 10 * 1000
  } else {
    gameLength = 30
    difficulty = "easy"
    lifetime = 4000
    bossHealth = 3
    regularHealth = 1
    respawnDelayMin = 3 * 1000
    respawnDelayMax = 7 * 1000
  }

  state = "ready"
  seenEvents.clear()
  updateTargets()
  updateScoreboard()

  await sleep(3000)

  state = "game"
  score = 0
  secondsLeft = gameLength
  updateTargets()
  updateScoreboard()
  while (secondsLeft > 0) {
    if (state !== "game") return
    await sleep(1000)
    secondsLeft--
  }

  state = "end"
  updateTargets()
  updateScoreboard()

  const stats = readStats()
  if (score > stats.highScore) {
    stats.highScore = score
  }
  stats.playCount++
  writeStats(stats)

  res.redirect("/admin.html")
})

app.get("/c/end", async (req, res) => {
  state = "end"
  updateTargets()
  updateScoreboard()
  res.redirect("/admin.html")
})

app.get("/c/test", async (req, res) => {
  state = "test"
  updateTargets()
  updateScoreboard()
  res.redirect("/admin.html")
})

app.get("/c/death", async (req, res) => {
  receiveTargetEvent("test", {
    event: TargetEvent.RegularDeath,
    millis: Date.now(),
  })
  res.redirect("/admin.html")
})

app.get("/c/boss", async (req, res) => {
  receiveTargetEvent("test", {
    event: TargetEvent.BossAppear,
    millis: Date.now(),
  })
  res.redirect("/admin.html")
})

app.get("/c/boss-death", async (req, res) => {
  receiveTargetEvent("test", {
    event: TargetEvent.BossDeath,
    millis: Date.now(),
  })
  res.redirect("/admin.html")
})

app.get("/c/update", async (req, res) => {
  for (var i = 0; i < 5; i++) {
    port?.write(JSON.stringify({ update: true }) + "\n")
  }
  res.redirect("/admin.html")
})
