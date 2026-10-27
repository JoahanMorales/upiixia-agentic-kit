# Stack · Expo (React Native, Expo Router, TypeScript)

Setup for the first task and structure reference. Conventions: the `stack-expo` skill (+ `vercel-react-best-practices`).

## Structure

```text
app/_layout.tsx                # owner: setup (tabs/stack); nobody edits it after
app/<f>.tsx · app/<f>/         # one screen (or route folder) per task: Expo Router finds it by file name
components/<f>/                # its components
lib/                           # api client, theme, shared types; owner: setup / contract task
package.json · app.json        # single owner (setup)
```
A task reserves `app/<f>.tsx` (or `app/<f>/`) and `components/<f>/`.

## Setup (~5 min)

```bash
npx create-expo-app@latest . --template default
npx expo install expo-router
```

## Product smoke

```bash
bash .uak/bin/uak init-smoke --command "bash .uak/bin/design-lint && npm ci --prefer-offline --no-audit --no-fund --loglevel=error && npx tsc --noEmit && npx expo export --platform web --output-dir /tmp/uak-expo-export"
```
`expo export` builds the web bundle without a device: it proves the app compiles in the merge gate's clean clone.

## Run
`npx expo start --port $UAK_PORT` (web: press `w`; device: Expo Go on the same network)
