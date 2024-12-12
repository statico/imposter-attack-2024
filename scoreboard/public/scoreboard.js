const $ = document.querySelector.bind(document)
const $$ = document.querySelectorAll.bind(document)

const score = 0
const secondsLeft = 0

const MUSIC_VOLUME = 0.7

const gameMusicFiles = [
  // Download music into public/music/game and add them here
  "among-us-hide-and-seek.mp3",
]

const menuMusicFiles = [
  // Download music into public/music/menu and add them here
  "pigstep.mp3",
]

const deathSoundFiles = new Array(11)
  .fill(null)
  .map((_, i) => `death${i + 1}.mp3`)

const gameMusic = gameMusicFiles.map(
  (file) => new Howl({ src: [`/music/game/${file}`], loop: true }),
)
const menuMusic = menuMusicFiles.map(
  (file) => new Howl({ src: [`/music/menu/${file}`], loop: true }),
)
const deathSounds = deathSoundFiles.map(
  (file) => new Howl({ src: [`/sfx/${file}`] }),
)

const startSound = new Howl({ src: ["/sfx/round-start.mp3"] })
const endSound = new Howl({ src: ["/sfx/victory-crew.mp3"] })
const bossAppearSound = new Howl({ src: ["/sfx/impostor-roar.mp3"] })
const bossDeathSound = new Howl({ src: ["/sfx/boss-death.mp3"] })

let music = menuMusic[Math.floor(Math.random() * menuMusic.length)]
music.volume(0.5)
music.play()
$("#music").innerText = music._src

let ws = null
const connect = () => {
  if (ws && ws.readyState === WebSocket.OPEN) return
  ws = new WebSocket("ws://localhost:4000")
  ws.onopen = () => {
    console.log("Connected to server")
  }
  ws.onmessage = (event) => {
    processMessage(JSON.parse(event.data))
  }
  ws.onclose = () => {
    console.log("Disconnected from server")
    // setTimeout(connect, 1000)
    setTimeout(() => {
      document.location.reload()
    }, 2000)
  }
}
setInterval(connect, 2000)
connect()

let currentState = null

const goToState = (newState) => {
  $$(".screen").forEach((screen) => (screen.style.display = "none"))
  $(`#${newState}`).style.display = "block"

  if (currentState !== newState) {
    currentState = newState
    switch (newState) {
      case "idle":
        endSound.stop()
        music?.stop()
        music = menuMusic[Math.floor(Math.random() * menuMusic.length)]
        music.loop(true)
        music.volume(MUSIC_VOLUME)
        music.play()
        $("#music").innerText = music._src
        break
      case "ready":
        music?.stop()
        startSound.play()
        music = gameMusic[Math.floor(Math.random() * gameMusic.length)]
        music.play()
        music.fade(0, MUSIC_VOLUME, 5000)
        break
      case "game":
        $("#music").innerText = music._src
        break
      case "end":
        music.fade(MUSIC_VOLUME, 0, 500)
        const m = music
        m.once("fade", () => {
          m.stop()
        })
        endSound.play()
        break
    }
  }
}

goToState("idle")

const processMessage = (message) => {
  // console.log("Received message", message)
  if (message.state) {
    goToState(message.state)
    $$(".score .lower").forEach((el) => {
      el.innerText = message.score
    })
    $$(".time .lower").forEach((el) => {
      el.innerText = message.secondsLeft
    })
  } else if (message.event) {
    switch (message.event) {
      case "regular-death":
        const sound =
          deathSounds[Math.floor(Math.random() * deathSounds.length)]
        sound.play()
        break
      case "boss-appear":
        bossAppearSound.play()
        break
      case "boss-death":
        bossDeathSound.play()
        break
    }
  }
  if (message.stats) {
    $("#high-score").innerText = "High Score: " + message.stats.highScore
  }
}

const astronauts = new Array(10).fill(null).map((_, i) => {
  const el = document.createElement("div")
  el.style.backgroundImage = "url('/astronaut.png')"
  el.style.backgroundSize = "contain"
  el.style.backgroundPosition = "center"
  el.style.backgroundRepeat = "no-repeat"
  el.style.position = "absolute"
  el.style.top = "-500px"
  el.style.left = "-500px"
  el.style.width = "100px"
  el.style.height = "100px"
  el.style.zIndex = -1
  el.style.opacity = 0.5
  el.dataset.dx = -10
  el.dataset.dy = -10
  el.dataset.scale = 1.0
  el.dataset.rotation = 10
  document.body.appendChild(el)
  return el
})

const animate = () => {
  astronauts.forEach((el, i) => {
    const rect = el.getBoundingClientRect()
    const l = rect.left
    const t = rect.top
    const r = rect.right
    const b = rect.bottom

    const w = window.innerWidth
    const h = window.innerHeight

    const m = 100
    if (r < -m || l > w + m || b < -m || t > h + m) {
      const z = Math.random() * (Math.PI * 2)
      let newX = Math.cos(z) * 100
      if (newX > 0) newX += w
      let newY = Math.sin(z) * 100
      if (newY > 0) newY += h
      el.style.left = `${newX}px`
      el.style.top = `${newY}px`

      const dir = Math.random() * (Math.PI * 2)
      const mag = Math.random() * 2 + 1
      el.dataset.dx = Math.cos(dir) * mag
      el.dataset.dy = Math.sin(dir) * mag

      el.dataset.rotation = Math.random() * 20

      const s = Math.random() * 0.4
      el.dataset.scale = s + 0.8
      el.style.opacity = s * 0.5 + 0.3
    }

    const x = parseFloat(el.style.left)
    const y = parseFloat(el.style.top)

    const { dx, dy, scale, rotation } = el.dataset
    const rot = (Date.now() / (10 + parseFloat(rotation))) % 360
    el.style.transform = `rotate(${rot}deg) scale(${parseFloat(scale)})`
    el.style.left = `${x + parseFloat(dx)}px`
    el.style.top = `${y + parseFloat(dy)}px`
  })
  requestAnimationFrame(animate)
}

animate()

window.addEventListener("dblclick", () => {
  switch (currentState) {
    case "idle":
      fetch("/c/new")
      break
    case "ready":
      break
    case "game":
      fetch("/c/end")
      break
    case "end":
      fetch("/c/menu")
      break
  }
})
