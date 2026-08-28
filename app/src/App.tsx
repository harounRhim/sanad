import { lazy, Suspense } from "react";
import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import RequireAuth from "./components/RequireAuth";
import Spinner from "./components/Spinner";
// Eager: the two screens a session actually lands on — Journey (signed-in
// index) and Login (signed-out redirect target). Everything else is
// code-split below; the production bundle was a single 521 kB chunk before
// this (Vite's own build warning), most of it screens a given session never
// opens.
import Journey from "./screens/Journey";
import Login from "./screens/Login";

const SurahDetail = lazy(() => import("./screens/SurahDetail"));
const SurahIndex = lazy(() => import("./screens/SurahIndex"));
const Search = lazy(() => import("./screens/Search"));
const Practice = lazy(() => import("./screens/Practice"));
const Drills = lazy(() => import("./screens/Drills"));
const Memorization = lazy(() => import("./screens/Memorization"));
const Review = lazy(() => import("./screens/Review"));
const ListenRepeat = lazy(() => import("./screens/ListenRepeat"));
const DueForRework = lazy(() => import("./screens/DueForRework"));
const Streak = lazy(() => import("./screens/Streak"));
const Reader = lazy(() => import("./screens/Reader"));
const Reciters = lazy(() => import("./screens/Reciters"));
const Bookmarks = lazy(() => import("./screens/Bookmarks"));
const Settings = lazy(() => import("./screens/Settings"));
const TajweedLegend = lazy(() => import("./screens/TajweedLegend"));
const AudioPlayer = lazy(() => import("./screens/AudioPlayer"));
const ResetPassword = lazy(() => import("./screens/ResetPassword"));

export default function App() {
  return (
    <Suspense fallback={<div className="p-6"><Spinner label="Loading…" /></div>}>
      <Routes>
        <Route path="login" element={<Login />} />
        <Route path="reset-password" element={<ResetPassword />} />
        <Route element={<RequireAuth />}>
          <Route element={<Layout />}>
            <Route index element={<Journey />} />
            <Route path="surah/:id" element={<SurahDetail />} />
            <Route path="surahs" element={<SurahIndex />} />
            <Route path="search" element={<Search />} />
            <Route path="practice" element={<Practice />} />
            <Route path="drills" element={<Drills />} />
            <Route path="memorization" element={<Memorization />} />
            <Route path="review" element={<Review />} />
            <Route path="listen/:surah" element={<ListenRepeat />} />
            <Route path="due" element={<DueForRework />} />
            <Route path="streak" element={<Streak />} />
            <Route path="read/:surah" element={<Reader />} />
            <Route path="reciters" element={<Reciters />} />
            <Route path="bookmarks" element={<Bookmarks />} />
            <Route path="legend" element={<TajweedLegend />} />
            <Route path="player" element={<AudioPlayer />} />
            <Route path="settings" element={<Settings />} />
            <Route path="*" element={<Journey />} />
          </Route>
        </Route>
      </Routes>
    </Suspense>
  );
}
